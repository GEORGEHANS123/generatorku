import os
import json
import re
import datetime 
import random
import requests
import pandas as pd # type: ignore
import mysql.connector # type: ignore
import math 
from collections import Counter 

from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv # type: ignore

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'your_super_secret_key_here_ganti_ini_di_produksi')

UPLOAD_FOLDER = 'datasets'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'csv'}

DATASETS = {
    'SD': os.path.join(UPLOAD_FOLDER, 'SD_100.csv'),
    'SMP': os.path.join(UPLOAD_FOLDER, 'SMP_100.csv'),
    'SMA': os.path.join(UPLOAD_FOLDER, 'SMA_100.csv')
}

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'generatorku_db'
}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        try:
            db = g._database = mysql.connector.connect(**MYSQL_CONFIG)
            print("DEBUG: Koneksi database MySQL berhasil dibuat.")
        except mysql.connector.Error as err:
            print(f"Error: Gagal terhubung ke database MySQL: {err}")
            flash(f"Gagal terhubung ke database: {err}", 'error')
            raise
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None and db.is_connected():
        db.close()
        print("DEBUG: Koneksi database MySQL ditutup.")

def init_db_mysql():
    conn = None
    try:
        conn = mysql.connector.connect(
            host=MYSQL_CONFIG['host'],
            user=MYSQL_CONFIG['user'],
            password=MYSQL_CONFIG['password']
        )
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
            print(f"DEBUG: Database '{MYSQL_CONFIG['database']}' dipastikan ada.")
        except mysql.connector.Error as err:
            print(f"Error saat membuat database: {err}")

        conn.database = MYSQL_CONFIG['database']
        
        schema_path = os.path.join(app.root_path, 'schema.sql')
        if not os.path.exists(schema_path):
            print(f"Error: schema.sql tidak ditemukan di {schema_path}. Pastikan file ini ada di root proyek.")
            return

        with open(schema_path, mode='r') as f:
            sql_script = f.read()
            commands = [cmd.strip() for cmd in sql_script.split(';') if cmd.strip()]
            for command in commands:
                if command:
                    try:
                        cursor.execute(command)
                    except mysql.connector.Error as err:
                        if "table exists" not in str(err).lower() and "already exists" not in str(err).lower():
                            print(f"Error saat menjalankan perintah SQL: {command}\nError: {err}")
            conn.commit()
        print("DEBUG: Tabel database MySQL berhasil diinisialisasi dari schema.sql.")
    except mysql.connector.Error as err:
        print(f"Error saat inisialisasi database MySQL: {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.before_first_request
def setup_database_and_admin():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        print(f"DEBUG: Direktori '{app.config['UPLOAD_FOLDER']}' berhasil dibuat.")

    for level, path in DATASETS.items():
        if not os.path.exists(path):
            print(f"Peringatan: File dataset default {path} tidak ditemukan. Kuis manual untuk level {level} mungkin tidak berfungsi sepenuhnya.")
            print(f"Mencoba membuat file placeholder {path}...")
            try:
                pd.DataFrame(columns=['TOPIK', 'SOAL', 'OPSI_A', 'OPSI_B', 'OPSI_C', 'OPSI_D', 'JAWABAN']).to_csv(path, sep=';', index=False)
                print(f"File placeholder {path} berhasil dibuat.")
            except Exception as e:
                print(f"Gagal membuat file placeholder {path}: {e}")

    init_db_mysql()

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", ('admin',))
        admin_exists = cursor.fetchone()
        if not admin_exists:
            hashed_password = generate_password_hash("adminpass", method='pbkdf2:sha256')
            cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)", ('admin', hashed_password, True))
            conn.commit()
            print("DEBUG: User admin 'admin' dibuat dengan password 'adminpass'. HARAP GANTI PASSWORD INI SEGERA!")
        else:
            print("DEBUG: User admin 'admin' sudah ada.")
    except mysql.connector.Error as err:
        print(f"Error saat setup admin: {err}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('Anda harus login untuk mengakses halaman ini.', 'warning')
            print("DEBUG: Mengarahkan ke halaman login.")
            return redirect(url_for('login'))
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, username, is_admin FROM users WHERE id = %s", (session['user_id'],))
        user_check = cursor.fetchone()
        cursor.close()

        if not user_check:
            flash('Sesi Anda tidak valid. Silakan login kembali.', 'warning')
            session.pop('logged_in', None)
            session.pop('user_id', None)
            session.pop('username', None)
            session.pop('is_admin', None)
            print(f"Peringatan: User ID {session.get('user_id')} di sesi tidak ditemukan di database. Melakukan logout.")
            return redirect(url_for('login'))

        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('Anda harus login untuk mengakses halaman ini.', 'warning')
            return redirect(url_for('login'))
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        cursor.close()

        if not user or not user['is_admin']:
            flash('Anda tidak memiliki izin untuk mengakses halaman ini.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# NEW: Function to import questions from CSV to quiz_questions table
def import_questions_from_csv_to_db(filepath, level_context=None):
    imported_count = 0
    try:
        df = pd.read_csv(filepath, sep=';', engine='python')
        required_columns = ['TOPIK', 'SOAL', 'OPSI_A', 'OPSI_B', 'OPSI_C', 'OPSI_D', 'JAWABAN']
        
        if not all(col in df.columns for col in required_columns):
            print(f"Error: CSV file {filepath} does not have required columns: {required_columns}.")
            return 0

        db = get_db()
        cursor = db.cursor()
        
        # Determine level for the imported questions
        level_to_import = level_context if level_context else "Unknown"
        # Try to infer level from filename (e.g., "SD_100.csv" -> "SD")
        filename_only = os.path.basename(filepath)
        match_level_in_filename = re.match(r'([A-Za-z]+)_', filename_only)
        if match_level_in_filename:
            level_to_import = match_level_in_filename.group(1).upper()
            if level_to_import not in ['SD', 'SMP', 'SMA']: # Only allow predefined levels
                level_to_import = "Unknown"
        
        # Clear existing questions for this level before importing to prevent duplicates if re-importing
        # You might want to refine this: e.g., delete only questions from this specific dataset, not all
        cursor.execute("DELETE FROM quiz_questions WHERE level = %s", (level_to_import,))
        db.commit()
        print(f"DEBUG: Menghapus soal lama untuk level {level_to_import} sebelum mengimpor dari {filepath}.")


        for index, row in df.iterrows():
            try:
                question = str(row['SOAL']).strip()
                options_list = [
                    str(row['OPSI_A']).strip(),
                    str(row['OPSI_B']).strip(),
                    str(row['OPSI_C']).strip(),
                    str(row['OPSI_D']).strip()
                ]
                correct_answer = str(row['JAWABAN']).strip()

                if not question or not options_list or len(options_list) != 4 or not correct_answer or correct_answer not in options_list:
                    print(f"Warning: Baris {index+1} di CSV {filepath} dilewati karena data tidak lengkap atau tidak valid.")
                    continue

                options_json = json.dumps(options_list)
                
                cursor.execute(
                    "INSERT INTO quiz_questions (level, question, options, correct_answer) VALUES (%s, %s, %s, %s)",
                    (level_to_import, question, options_json, correct_answer)
                )
                imported_count += 1
            except Exception as row_e:
                print(f"Error memproses baris {index+1} dari {filepath}: {row_e}")
        
        db.commit()
        print(f"DEBUG: Berhasil mengimpor {imported_count} soal dari {filepath} ke quiz_questions.")
        
    except Exception as e:
        print(f"Error importing CSV {filepath} to DB: {e}")
        db.rollback()
    finally:
        cursor.close()
    return imported_count


def get_sample_questions_from_csv(level, num_samples=1):
    file_path = DATASETS.get(level)
    if not file_path or not os.path.exists(file_path):
        print(f"Peringatan: Dataset CSV default {level} tidak ditemukan di {file_path}")
        return ""

    try:
        df = pd.read_csv(file_path, sep=';', engine='python')
        if df.empty:
            print(f"Peringatan: Dataset CSV default {level} kosong.")
            return ""

        required_columns = ['TOPIK', 'SOAL', 'OPSI_A', 'OPSI_B', 'OPSI_C', 'OPSI_D', 'JAWABAN']
        if not all(col in df.columns for col in required_columns):
            print(f"Peringatan: Dataset CSV default {level} tidak memiliki kolom yang diperlukan: {required_columns}. Kolom yang ada: {df.columns.tolist()}")
            return ""

        sample_df = df.sample(min(num_samples, len(df)))

        samples = []
        for index, row in sample_df.iterrows():
            question = str(row['SOAL']).strip()
            options_list = [
                str(row['OPSI_A']).strip(),
                str(row['OPSI_B']).strip(),
                str(row['OPSI_C']).strip(),
                str(row['OPSI_D']).strip()
            ]
            correct_answer_text = str(row['JAWABAN']).strip()

            samples.append(
                f'{{"question": {json.dumps(question)}, '
                f'"options": [{json.dumps(options_list[0])}, {json.dumps(options_list[1])}, {json.dumps(options_list[2])}, {json.dumps(options_list[3])}], '
                f'"correct_answer": {json.dumps(correct_answer_text)}}}'
            )
        return "\n".join(samples)
    except Exception as e:
        print(f"Error saat mengambil sampel dari {file_path}: {e}")
        return ""

def fix_json_string(json_str):
    json_str = json_str.strip()
    json_str = json_str.replace('{{', '{').replace('}}', '}')
    json_str = re.sub(r'"\s*:\s*""', '', json_str)
    json_str = re.sub(r',\s*""\s*:\s*""', '', json_str)

    json_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', json_str)
    
    json_match = re.search(r'\[\s*\{.*\}\s*\]', json_str, re.DOTALL)
    if not json_match:
        json_match = re.search(r'\{\s*".*"\s*\}', json_str, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(0).strip()
    else:
        first_bracket = json_str.find('[')
        first_brace = json_str.find('{')

        if first_bracket == -1 and first_brace == -1:
            return json_str

        if first_bracket == -1 or (first_brace != -1 and first_brace < first_bracket):
            json_str = json_str[first_brace:]
        else:
            json_str = json_str[first_bracket:]

        last_bracket = json_str.rfind(']')
        last_brace = json_str.rfind('}')

        if last_bracket == -1 and last_brace == -1:
            return json_str

        if last_bracket == -1 or (last_brace != -1 and last_brace > last_bracket):
            json_str = json_str[:last_brace + 1]
        else:
            json_str = json_str[:last_bracket + 1]

    json_str = re.sub(r',\s*\]', ']', json_str)
    json_str = re.sub(r',\s*\}', '}', json_str)
    
    balance = 0
    for char in json_str:
        if char == '[':
            balance += 1
        elif char == ']':
            balance -= 1
        elif char == '{':
            balance += 1
        elif char == '}':
            balance -= 1
    
    if balance > 0:
        if json_str.startswith('['):
            json_str += ']' * balance
        elif json_str.startswith('{'):
            json_str += '}' * balance
    elif balance < 0:
        json_str = json_str[:len(json_str) + balance]
        
    return json_str

def calculate_correct_answer_and_options(question_text, ai_options, ai_correct_answer):
    original_question_text = question_text
    question_text_lower = question_text.lower()
    calculated_answer = None
    question_type = "unknown"

    cleaned_question_for_eval = question_text_lower.replace('x', '*').replace(':', '/')
    cleaned_question_for_eval = re.sub(r'(hasil dari|berapakah|adalah|=|\s*cm\^?\d*|\s*gram|\s*menit|\s*bulan|\s*tahun|\s*hari|\s*detik|\s*cm)', '', cleaned_question_for_eval).strip()
    
    def evaluate_sqrt_in_string(match):
        num = float(match.group(1))
        return str(math.sqrt(num))
    
    cleaned_question_for_eval = re.sub(r'akar kuadrat dari\s*(\d+)', evaluate_sqrt_in_string, cleaned_question_for_eval)
    cleaned_question_for_eval = re.sub(r'sqrt\((\d+)\)', evaluate_sqrt_in_string, cleaned_question_for_eval)

    cleaned_question_for_eval = re.sub(r'(\d+)\s*pangkat\s*(\d+)', r'(\1**\2)', cleaned_question_for_eval)

    cleaned_question_for_eval = re.sub(r'(\d+)\s*per\s*(\d+)', r'(\1/\2)', cleaned_question_for_eval)

    match_x_y_an_eval = re.search(r'(satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)\s*(\d+)-an', cleaned_question_for_eval)
    if match_x_y_an_eval:
        num_word_map = {
            'satu': 1, 'dua': 2, 'tiga': 3, 'empat': 4, 'lima': 5,
            'enam': 6, 'tujuh': 7, 'delapan': 8, 'sembilan': 9, 'sepuluh': 10
        }
        multiplier = num_word_map.get(match_x_y_an_eval.group(1))
        base_num = int(match_x_y_an_eval.group(2))
        if multiplier is not None:
            numeric_result = multiplier * base_num
            calculated_answer = str(numeric_result)
            question_type = "numeric"

    if re.search(r'\b\d+\b.*[+\-]\b\d+\b', cleaned_question_for_eval) and not calculated_answer:
        numeric_parts = re.findall(r'\d+', cleaned_question_for_eval)
        operators = re.findall(r'[+\-]', cleaned_question_for_eval)
        if len(numeric_parts) >= 2 and len(operators) >= 1:
            try:
                temp_eval_str = numeric_parts[0]
                for i in range(len(operators)):
                    temp_eval_str += operators[i] + numeric_parts[i+1]
                cleaned_question_for_eval = temp_eval_str
                question_type = "numeric"
            except Exception as e:
                print(f"DEBUG: Error building temp_eval_str: {e}")

    try:
        safe_dict = {
            "__builtins__": None,
            "abs": abs, "min": min, "max": max, "round": round,
            "math": math,
            "sqrt": math.sqrt,
            "pow": math.pow
        }
        
        if re.fullmatch(r'[-+]?\d+(\.\d+)?([+\-*/]\d+(\.\d+)?)*|\d+(\.\d+)?\*\*(-?\d+(\.\d+)?)?', cleaned_question_for_eval.strip()):
            calculated_answer_val = eval(cleaned_question_for_eval.strip(), safe_dict, {})
            calculated_answer = str(round(calculated_answer_val, 2))
            if calculated_answer.endswith('.0'): calculated_answer = str(int(float(calculated_answer)))
            question_type = "numeric"
            print(f"DEBUG: Calculated numeric answer using eval: {calculated_answer} from '{cleaned_question_for_eval}'")
        else:
            print(f"DEBUG: Cleaned question '{cleaned_question_for_eval}' not suitable for direct eval.")

    except (SyntaxError, NameError, TypeError, ZeroDivisionError, ValueError) as e:
        calculated_answer = None
        print(f"DEBUG: Eval failed for '{cleaned_question_for_eval}': {e}")
        
    if calculated_answer is None:
        match_arithmetic_fallback = re.search(r'(\d+)\s*([+\-xX*/])\s*(\d+)', question_text_lower)
        if match_arithmetic_fallback:
            num1 = float(match_arithmetic_fallback.group(1))
            operator = match_arithmetic_fallback.group(2)
            num2 = float(match_arithmetic_fallback.group(3))
            try:
                if operator == '+': calculated_answer = str(int(num1 + num2))
                elif operator == '-': calculated_answer = str(int(num1 - num2))
                elif operator in ('x', 'X', '*'): calculated_answer = str(int(num1 * num2))
                elif operator == '/' and num2 != 0: calculated_answer = str(round(num1 / num2, 2))
                question_type = "numeric"
            except Exception as e: pass

    if calculated_answer is None:
        match_modus = re.search(r'modus\s*dari\s*data\s*([\d\s,]+)', question_text_lower)
        if match_modus:
            data_str = match_modus.group(1)
            numbers = [int(n.strip()) for n in re.findall(r'\d+', data_str)]
            if numbers:
                counts = Counter(numbers)
                if counts:
                    max_count_val = max(counts.values())
                    modes = [k for k, v in counts.items() if v == max_count_val]
                    calculated_answer = str(min(modes))
                    question_type = "numeric"
                    print(f"DEBUG: Calculated mode: {calculated_answer}")

    if calculated_answer is None:
        match_nilai_tempat = re.search(r'nilai tempat\s*(\d+)\s*di\s*(\d+)', question_text_lower)
        if match_nilai_tempat:
            digit_to_find = match_nilai_tempat.group(1)
            number_str = match_nilai_tempat.group(2)
            try:
                idx = number_str.rfind(digit_to_find)
                if idx != -1:
                    position = len(number_str) - 1 - idx
                    place_names = ["satuan", "puluhan", "ratusan", "ribuan", "puluh ribuan"]
                    calculated_answer = place_names[position] if position < len(place_names) else None
                    question_type = "definition"
                    print(f"DEBUG: Calculated place value: {calculated_answer}")
            except Exception as e: pass

    if calculated_answer is None:
        match_unit_time = re.search(r'(\d+)\s*jam\s*=\s*\.\.\.\s*menit', question_text_lower)
        if match_unit_time:
            hours = int(match_unit_time.group(1))
            calculated_answer = str(hours * 60)
            question_type = "numeric"
            print(f"DEBUG: Calculated unit conversion (time): {calculated_answer}")
        
        match_unit_weight = re.search(r'(\d+)\s*kg\s*=\s*\.\.\.\s*gram', question_text_lower)
        if match_unit_weight:
            kg = int(match_unit_weight.group(1))
            calculated_answer = str(kg * 1000)
            question_type = "numeric"
            print(f"DEBUG: Calculated unit conversion (weight): {calculated_answer}")
        
        match_triwulan = re.search(r'(\d+)\s*triwulan\s*=\s*\.\.\.\s*bulan', question_text_lower)
        if match_triwulan:
            triwulan = int(match_triwulan.group(1))
            calculated_answer = str(triwulan * 3)
            question_type = "numeric"
            print(f"DEBUG: Calculated triwulan: {calculated_answer}")

    if calculated_answer is None:
        match_x_y_an = re.search(r'(satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)\s*(\d+)-an', question_text_lower)
        if match_x_y_an:
            num_word_map = {
                'satu': 1, 'dua': 2, 'tiga': 3, 'empat': 4, 'lima': 5,
                'enam': 6, 'tujuh': 7, 'delapan': 8, 'sembilan': 9, 'sepuluh': 10
            }
            multiplier = num_word_map.get(match_x_y_an.group(1))
            base_num = int(match_x_y_an.group(2))
            if multiplier is not None:
                numeric_result = multiplier * base_num
                calculated_answer = str(numeric_result)
                question_type = "numeric"
                if numeric_result == 100: calculated_answer = "seratusan"
                elif numeric_result == 200: calculated_answer = "duaratusan"
                elif numeric_result == 500: calculated_answer = "limaratusan"
                elif numeric_result == 1000: calculated_answer = "seribuan"
                elif numeric_result == 2000: calculated_answer = "duaribuan"
                elif numeric_result == 5000: calculated_answer = "limaribuan"
                elif numeric_result == 6000: calculated_answer = "enamribuan"
                elif numeric_result == 10000: calculated_answer = "sepuluhribuan"
                print(f"DEBUG: Calculated X Y-an: {calculated_answer}")

    if calculated_answer is None:
        match_comparison = re.search(r'([\d.,/]+)\s*\.\.\.\s*([\d.,/]+)\s*=', question_text_lower)
        if match_comparison:
            val1_str = match_comparison.group(1).replace(',', '.')
            val2_str = match_comparison.group(2).replace(',', '.')
            try:
                from fractions import Fraction
                val1 = Fraction(val1_str) if '/' in val1_str else Fraction(float(val1_str))
                val2 = Fraction(val2_str) if '/' in val2_str else Fraction(float(val2_str))

                if val1 == val2: calculated_answer = "="
                elif val1 > val2: calculated_answer = ">"
                else: calculated_answer = "<"
                question_type = "comparison"
                print(f"DEBUG: Calculated comparison: {calculated_answer}")
            except Exception as e: pass

    if calculated_answer is None:
        match_odd_even_between = re.search(r'(ganjil|genap)\s*antara\s*(\d+)\s*dan\s*(\d+)', question_text_lower)
        if match_odd_even_between:
            parity = match_odd_even_between.group(1)
            start_num = int(match_odd_even_between.group(2))
            end_num = int(match_odd_even_between.group(3))
            
            sequence = []
            for i in range(start_num + 1, end_num):
                if (parity == 'ganjil' and i % 2 != 0) or \
                   (parity == 'genap' and i % 2 == 0):
                    sequence.append(str(i))
            
            if sequence:
                calculated_answer = " ".join(sequence)
                question_type = "sequence"
                print(f"DEBUG: Calculated sequence: {calculated_answer}")

    if calculated_answer is None:
        match_keliling_sisi = re.search(r'keliling\s*(sisi|persegi)?\s*(\d+)\s*cm', question_text_lower)
        if match_keliling_sisi:
            side = int(match_keliling_sisi.group(2))
            calculated_answer = str(side * 4)
            question_type = "numeric"
            print(f"DEBUG: Calculated perimeter: {calculated_answer}")
        
        match_volume_sisi = re.search(r'volume\s*(sisi|kubus)?\s*(\d+)\s*cm', question_text_lower)
        if match_volume_sisi:
            side = int(match_volume_sisi.group(2))
            calculated_answer = str(side ** 3)
            question_type = "numeric"
            print(f"DEBUG: Calculated volume (cube): {calculated_answer}")

    if calculated_answer is None:
        definition_map = {
            "satuan suhu": "celcius",
            "satuan berat baku": "kilogram",
            "nilai tengah urut": "median",
            "nilai tengah dari data yang sudah diurutkan": "median",
            "perubahan waktu": "durasi",
            "urutan bulan": "januari februari maret",
            "diagram batang": "batang",
            "diagram gambar": "piktogram",
            "ukur panjang": "penggaris",
            "lambang seratus tujuh": "107"
        }
        calculated_answer = definition_map.get(question_text_lower, calculated_answer)
        if calculated_answer is not None:
            question_type = "definition"
            print(f"DEBUG: Calculated definition: {calculated_answer}")


    final_options = []
    
    cleaned_ai_options = [str(opt).strip() for opt in ai_options if str(opt).strip()]
    
    if calculated_answer is not None:
        final_correct_answer = calculated_answer
        
        if question_type == "numeric":
            numeric_options_filtered = []
            for opt in cleaned_ai_options:
                if re.fullmatch(r'-?\d+(\.\d+)?|\d+/\d+', opt.replace(',', '.')) or \
                   opt in ["seratusan", "duaratusan", "limaratusan", "seribuan", "duaribuan", "limaribuan", "enamribuan", "sepuluhribuan"]:
                    numeric_options_filtered.append(opt)
                else:
                    print(f"DEBUG: Removing non-numeric option '{opt}' for numeric question: {original_question_text}")
            
            final_options = list(set(numeric_options_filtered))
            
            if final_correct_answer not in final_options:
                if len(final_options) < 4:
                    final_options.append(final_correct_answer)
                else:
                    incorrect_to_replace = [opt for opt in final_options if opt != final_correct_answer]
                    if incorrect_to_replace:
                        final_options.remove(random.choice(incorrect_to_replace))
                        final_options.append(final_correct_answer)
                    else:
                        if len(final_options) < 4: final_options.append(final_correct_answer)


            while len(final_options) < 4:
                try:
                    if isinstance(final_correct_answer, (int, float)):
                        base_val = float(final_correct_answer)
                    elif final_correct_answer.replace('.', '', 1).isdigit():
                        base_val = float(final_correct_answer)
                    else:
                        word_to_num_map = {
                            "seratusan": 100, "duaratusan": 200, "limaratusan": 500,
                            "seribuan": 1000, "duaribuan": 2000, "limaribuan": 5000,
                            "enamribuan": 6000, "sepuluhribuan": 10000
                        }
                        base_val = word_to_num_map.get(final_correct_answer, 0)
                        if base_val == 0: base_val = random.randint(10, 100)
                    
                    distractor_val = base_val + random.choice([-1, 1]) * random.uniform(0.1, max(1.0, base_val * 0.1))
                    
                    if base_val >= 1000: distractor_val = base_val + random.choice([-1, 1]) * random.randint(1, 3) * 100
                    elif base_val >= 100: distractor_val = base_val + random.choice([-1, 1]) * random.randint(1, 5) * 10
                    elif base_val >= 10: distractor_val = base_val + random.choice([-1, 1]) * random.randint(1, 3)
                    
                    distractor = str(round(distractor_val, 2))
                    if distractor.endswith('.0'): distractor = str(int(float(distractor)))
                    
                    if distractor not in final_options:
                        final_options.append(distractor)
                except Exception as e:
                    print(f"DEBUG: Failed to generate numeric distractor for {final_correct_answer}: {e}")
                    if len(final_options) < 4: final_options.append(str(random.randint(1, 100)))

            final_options = list(set(final_options))
            if len(final_options) > 4: final_options = random.sample(final_options, 4)
            while len(final_options) < 4: final_options.append(str(random.randint(1, 100)))
            random.shuffle(final_options)

        elif question_type == "definition" or question_type == "comparison" or question_type == "sequence" or question_type == "unknown":
            known_relevant_options = {
                "satuan suhu": ["celcius", "fahrenheit", "kelvin", "reamur"],
                "satuan berat baku": ["kilogram", "gram", "ton", "kuintal"],
                "nilai tempat": ["satuan", "puluhan", "ratusan", "ribuan"],
                "nilai tengah urut": ["rata-rata", "median", "modus", "jangkauan"],
                "nilai tengah dari data yang sudah diurutkan": ["rata-rata", "median", "modus", "jangkauan"],
                "perubahan waktu": ["durasi", "interval", "periode", "waktu"],
                "urutan bulan": ["januari februari maret", "april mei juni", "juli agustus september", "oktober november desember"],
                "diagram batang": ["batang", "garis", "lingkaran", "piktogram"],
                "diagram gambar": ["piktogram", "garis", "lingkaran", "batang"],
                "ukur panjang": ["penggaris", "meteran", "timbangan", "jam", "gelas ukur"],
                "lambang seratus tujuh": ["107", "1007", "170", "701"],
                "1/2 ... 0,5 =": ["=", ">", "<", "!="],
            }
            
            plausible_options = []
            if question_text_lower in known_relevant_options:
                plausible_options = [opt for opt in cleaned_ai_options if opt in known_relevant_options[question_text_lower]]
            
            final_options = list(set(plausible_options))

            if final_correct_answer not in final_options:
                if len(final_options) < 4:
                    final_options.append(final_correct_answer)
                else:
                    incorrect_to_replace = [opt for opt in final_options if opt != final_correct_answer]
                    if incorrect_to_replace:
                        final_options.remove(random.choice(incorrect_to_replace))
                        final_options.append(final_correct_answer)
                    else:
                        if len(final_options) < 4: final_options.append(final_correct_answer)
            
            remaining_needed = 4 - len(final_options)
            if remaining_needed > 0:
                potential_distractors = []
                if question_text_lower in known_relevant_options:
                    potential_distractors = [opt for opt in known_relevant_options[question_text_lower] if opt not in final_options]
                
                while len(final_options) < 4 and potential_distractors:
                    distractor = random.choice(potential_distractors)
                    final_options.append(distractor)
                    potential_distractors.remove(distractor)

                while len(final_options) < 4:
                    generic_opt_base = "Opsi "
                    if question_type == "sequence" and final_correct_answer and ' ' in final_correct_answer:
                        parts = final_correct_answer.split(' ')
                        if len(parts) > 1:
                            modified_parts = list(parts)
                            idx_to_change = random.randint(0, len(modified_parts) - 1)
                            try: num = int(modified_parts[idx_to_change]); modified_parts[idx_to_change] = str(num + random.choice([-1, 1]))
                            except ValueError: pass
                            generic_opt_base = " ".join(modified_parts) + " (generik)"
                    
                    distractor_to_add = f"{generic_opt_base}{random.randint(1,100)}" if generic_opt_base.startswith("Opsi") else generic_opt_base
                    if distractor_to_add not in final_options:
                        final_options.append(distractor_to_add)

            random.shuffle(final_options)

    else:
        final_correct_answer = str(ai_correct_answer).strip() if ai_correct_answer else ""
        final_options = [str(opt).strip() for opt in ai_options if str(opt).strip()]
        
        if len(final_options) > 4:
            final_options = random.sample(final_options, 4)
        elif len(final_options) < 4:
            while len(final_options) < 4:
                final_options.append(f"Opsi generik {len(final_options) + 1}")
        
        if final_correct_answer not in final_options:
            if len(final_options) > 0:
                final_options[random.randint(0, len(final_options) - 1)] = final_correct_answer
            else:
                final_options = [final_correct_answer, "Opsi 1", "Opsi 2", "Opsi 3"]
        
        random.shuffle(final_options)

    return original_question_text, final_options, final_correct_answer


@app.route('/')
def home():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"DEBUG: Mencoba login untuk username: {username}")

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, username, password, is_admin FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            flash('Login berhasil!', 'success')
            print(f"DEBUG: Login berhasil untuk user_id: {session['user_id']}, username: {session['username']}, is_admin: {session['is_admin']}")
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'error')
            print("DEBUG: Login gagal: username atau password salah.")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"DEBUG: Mencoba registrasi untuk username: {username}")

        if not username or not password:
            flash('Username dan password harus diisi.', 'error')
            return render_template('register.html')

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()
        cursor.close()

        if existing_user:
            flash('Username sudah ada. Pilih username lain.', 'error')
            return render_template('register.html')

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        try:
            db_conn = get_db()
            cursor = db_conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
            db_conn.commit()
            cursor.close()
            flash('Registrasi berhasil! Silakan login.', 'success')
            print(f"DEBUG: Registrasi berhasil untuk username: {username}. Mengarahkan ke login.")
            return redirect(url_for('login'))
        except mysql.connector.Error as e:
            flash(f'Gagal registrasi: {str(e)}', 'error')
            if db_conn:
                db_conn.rollback()
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    session.pop('current_quiz_id', None)
    session.pop('temp_quiz_items', None)
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    print(f"DEBUG: Mengambil riwayat kuis untuk user_id: {session['user_id']}")
    cursor.execute("SELECT id, level, topic, score, total_questions, timestamp FROM quiz_history WHERE user_id = %s ORDER BY timestamp DESC", (session['user_id'],))
    history = cursor.fetchall()
    cursor.close()
    print(f"DEBUG: Ditemukan {len(history)} riwayat kuis untuk user_id: {session['user_id']}")
    return render_template('includes/dashboard.html', history=history, username=session['username']) 

@app.route('/quiz')
@login_required
def quiz():
    quiz_type = request.args.get('type')
    level = request.args.get('level')
    num_questions = request.args.get('num_questions', type=int)
    topic = request.args.get('topic')
    level_context = request.args.get('level_context')

    print(f"DEBUG: Memulai rute /quiz. Tipe: {quiz_type}, Topik: {topic}, Level: {level}, Level Konteks: {level_context}, Jumlah Soal: {num_questions}")
    print(f"DEBUG: session['user_id'] di /quiz: {session.get('user_id')}")

    session.pop('temp_quiz_items', None)
    session.pop('current_quiz_id', None)

    try:
        if quiz_type == 'manual':
            response = requests.post(
                url_for('api_generate_quiz', _external=True),
                json={'level': level, 'num_questions': num_questions},
                headers={'Content-Type': 'application/json', 'Cookie': request.headers.get('Cookie')}
            )
            response.raise_for_status()
            data = response.json()
            quiz_data = data.get('quiz', [])
            quiz_history_id = data.get('quiz_history_id')
            print(f"DEBUG: API Manual Quiz Response: quiz_history_id={quiz_history_id}, quiz_data_len={len(quiz_data)}")

        elif quiz_type == 'ai':
            response = requests.post(
                url_for('api_generate_quiz_ai', _external=True),
                json={'topic': topic, 'num_questions': num_questions, 'level_context': level_context},
                headers={'Content-Type': 'application/json', 'Cookie': request.headers.get('Cookie')}
            )
            response.raise_for_status()
            data = response.json()
            quiz_data = data.get('quiz', [])
            quiz_history_id = data.get('quiz_history_id')
            print(f"DEBUG: API AI Quiz Response: quiz_history_id={quiz_history_id}, quiz_data_len={len(quiz_data)}")

        else:
            flash("Tipe kuis tidak valid.", 'error')
            return redirect(url_for('dashboard'))

        if not quiz_data:
            flash('Gagal menghasilkan kuis. Tidak ada soal yang valid.', 'error')
            return redirect(url_for('dashboard'))
        
        if not quiz_history_id:
            flash('Error: ID kuis tidak ditemukan setelah generasi. Silakan coba lagi.', 'error')
            return redirect(url_for('dashboard'))

        session['temp_quiz_items'] = quiz_data
        session['current_quiz_id'] = quiz_history_id

        return render_template('quiz.html',
                               quiz_data_json=json.dumps(quiz_data),
                               quiz_history_id=quiz_history_id,
                               quiz_type=quiz_type,
                               topic=topic,
                               level=level,
                               num_questions=num_questions,
                               level_context=level_context)

    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_json = e.response.json()
                error_message = error_json.get('error', error_message)
            except json.JSONDecodeError:
                pass
        flash(f"Gagal memuat kuis: {error_message}. Pastikan Ollama berjalan dan model 'llama3' sudah diunduh jika menggunakan AI.", 'error')
        print(f"ERROR: RequestException di /quiz ({quiz_type}): {e}")
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f"Terjadi kesalahan tak terduga saat memuat kuis: {e}", 'error')
        print(f"ERROR: Exception di /quiz ({quiz_type}): {e}")
        return redirect(url_for('dashboard'))


@app.route('/api/generate_quiz', methods=['POST'])
@login_required
def api_generate_quiz():
    data = request.json
    level = data.get('level')
    num_questions = data.get('num_questions', 5)
    user_id = session.get('user_id')

    print(f"DEBUG: api_generate_quiz (Manual) dipanggil oleh user_id: {user_id} untuk level: {level}, jumlah soal: {num_questions}")

    db = get_db()
    cursor = db.cursor()
    quiz_history_id = None
    try:
        cursor.execute(
            "INSERT INTO quiz_history (user_id, level, topic, score, total_questions, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, level, 'Manual', 0, num_questions, datetime.datetime.now())
        )
        db.commit()
        quiz_history_id = cursor.lastrowid
        print(f"DEBUG: quiz_history_id (Manual API) berhasil dibuat: {quiz_history_id}")
    except mysql.connector.Error as e:
        print(f"Error saving manual quiz to DB: {e}")
        db.rollback()
        return jsonify({"error": f"Gagal menyimpan riwayat kuis awal: {str(e)}"}), 500
    finally:
        cursor.close()


    quiz_items = []
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT id, question, options, correct_answer FROM quiz_questions WHERE level = %s ORDER BY RAND() LIMIT %s", (level, num_questions))
    questions_from_db = cursor.fetchall()
    
    questions_to_return = []
    try:
        quiz_taken_cursor = db.cursor()
        for q in questions_from_db:
            try:
                options_list = json.loads(q['options'])
                if len(options_list) >= 4 and q['correct_answer'] in options_list:
                    quiz_taken_cursor.execute(
                        "INSERT INTO quiz_taken_questions (quiz_history_id, question_text, options_json, correct_answer, user_answer, is_correct) VALUES (%s, %s, %s, %s, %s, %s)",
                        (quiz_history_id, q['question'], json.dumps(options_list), q['correct_answer'], None, None)
                    )
                    questions_to_return.append({
                        'id': quiz_taken_cursor.lastrowid,
                        'question': q['question'],
                        'options': options_list,
                        'correct_answer': q['correct_answer']
                    })
                else:
                    print(f"Warning: Soal dari DB tidak valid (opsi < 4 atau jawaban tidak ada di opsi): {q['question']}")
            except json.JSONDecodeError as e:
                print(f"Warning: Opsi soal dari DB tidak valid JSON: {q['options']} - {e}")
            except Exception as e:
                print(f"Warning: Error memproses soal dari DB: {e} - {q['question']}")
        db.commit()
        print(f"DEBUG: Detail soal kuis manual disimpan ke quiz_taken_questions untuk quiz_history_id: {quiz_history_id}")
    except mysql.connector.Error as e:
        print(f"Error saving questions to quiz_taken_questions: {e}")
        db.rollback()
        return jsonify({"error": f"Gagal menyimpan detail soal: {str(e)}"}), 500
    finally:
        quiz_taken_cursor.close()
    
    quiz_items = questions_to_return

    cursor.close()

    if not quiz_items:
        return jsonify({"error": "Tidak ada soal yang tersedia untuk level ini."}), 404

    return jsonify({"quiz": quiz_items[:num_questions], "quiz_history_id": quiz_history_id}) 

@app.route('/api/generate_quiz_ai', methods=['POST'])
@login_required
def api_generate_quiz_ai():
    data = request.json
    topic = data.get('topic')
    num_questions = data.get('num_questions', 1)
    level_context = data.get('level_context', 'SD')
    user_id = session.get('user_id')

    print(f"DEBUG: api_generate_quiz_ai (AI) dipanggil oleh user_id: {user_id} untuk topik: {topic}, level: {level_context}, jumlah soal: {num_questions}")

    db = get_db()
    cursor = db.cursor()
    quiz_history_id = None
    try:
        cursor.execute(
            "INSERT INTO quiz_history (user_id, level, topic, score, total_questions, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, level_context, topic, 0, num_questions, datetime.datetime.now())
        )
        db.commit()
        quiz_history_id = cursor.lastrowid
        print(f"DEBUG: quiz_history_id (AI API) berhasil dibuat: {quiz_history_id}")
    except mysql.connector.Error as e:
        print(f"Error saving AI quiz to DB: {e}")
        db.rollback()
        return jsonify({"error": f"Gagal menyimpan riwayat kuis AI awal: {str(e)}"}), 500
    finally:
        cursor.close()


    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT question, options, correct_answer FROM quiz_questions WHERE level = %s ORDER BY RAND() LIMIT 1", (level_context,))
        context_sample_db = cursor.fetchone()
        cursor.close()

        context_samples_str = ""
        if context_sample_db:
            options_list = json.loads(context_sample_db['options'])
            if len(options_list) == 4 and context_sample_db['correct_answer'] in options_list:
                context_samples_str = (
                    f'{{"question": {json.dumps(context_sample_db["question"])}, '
                    f'"options": [{json.dumps(options_list[0])}, {json.dumps(options_list[1])}, {json.dumps(options_list[2])}, {json.dumps(options_list[3])}], '
                    f'"correct_answer": {json.dumps(context_sample_db["correct_answer"])}}}' # FIX: changed context_list to context_sample_db
                )
            else:
                print(f"Warning: Contoh soal dari DB tidak valid untuk few-shot: {context_sample_db['question']}")
        
        if not context_samples_str:
            context_samples_str = get_sample_questions_from_csv(level_context, num_samples=1)
            if not context_samples_str:
                 print("Warning: Tidak ada contoh soal valid dari DB maupun CSV default untuk few-shot learning.")


        ollama_api_url = "http://localhost:11434/api/generate"
        model_name = "llama3" 

        prompt_message = f"""
        Anda adalah pembuat soal kuis matematika yang presisi dan **AKURAT 100%**.
        Buat **TEPAT {num_questions} soal** pilihan ganda baru.
        Soal-soal ini **HARUS** mengenai topik **{topic}** dan **khususnya BERSIFAT MATEMATIKA MURNI** (bukan sekadar tentang '{topic}' secara umum, tapi operasi/konsep matematika langsung).
        Tingkat kesulitan dan gaya soal harus **mirip dengan soal {level_context}** dan **sesuai untuk anak-anak {level_context}**.
        
        **Fokus utama adalah soal-soal sederhana, langsung, dan berbasis perhitungan atau konsep dasar.**
        **JANGAN membuat soal cerita yang panjang, skenario rumit, atau pertanyaan yang membutuhkan banyak konteks.**
        **Contoh soal yang diharapkan (fokus pada perhitungan langsung, semua opsi adalah angka):**
        - "Hasil dari 5 + 3 adalah..." (Opsi: 7, 8, 9, 10. Jawaban: 8)
        - "Angka setelah 10 adalah..." (Opsi: 9, 10, 11, 12. Jawaban: 11)
        - "Bentuk desimal dari 3/4 adalah..." (Opsi: 0.25, 0.50, 0.75, 1.00. Jawaban: 0.75)
        - "Akar kuadrat dari 49 adalah..." (Opsi: 6, 7, 8, 9. Jawaban: 7)
        - "Modus dari data 5, 7, 5, 8, 9 adalah..." (Opsi: 5, 6, 7, 8. Jawaban: 5)
        - "2 kg = ... gram" (Opsi: 20, 200, 2000, 0.002. Jawaban: 2000)
        - "Pembulatan 67 ke puluhan terdekat adalah..." (Opsi: 60, 65, 70, 80. Jawaban: 70)
        - "Dua 500-an = ..." (Opsi: 500, 1000, 1500, 2000. Jawaban: 1000)
        - "Tiga 2000-an = ..." (Opsi: 2000, 4000, 6000, 8000. Jawaban: 6000)
        - "Nilai tengah dari data yang sudah diurutkan adalah..." (Opsi: rata-rata, median, modus, jangkauan. Jawaban: median)
        - "Satuan berat baku adalah..." (Opsi: meter, liter, kilogram, detik. Jawaban: kilogram)
        - "Satuan suhu adalah..." (Opsi: meter, kilogram, celcius, liter. Jawaban: celcius)
        - "1/2 ... 0,5 =" (Opsi: =, >, !=, <. Jawaban: =)
        - "Volume sisi 3 cm =" (Opsi: 9, 12, 27, 81. Jawaban: 27)
        - "Ganjil antara 10 dan 20 =" (Opsi: "10 12 14 16 18", "11 13 15 17 19", "12 14 16 18 20", "11 12 13 14 15". Jawaban: "11 13 15 17 19")
        - "5 x 6 - 15 : 3 =" (Opsi: 5, 15, 25, 35. Jawaban: 25)
        - "Buku 5000 + pensil 1000 =" (Opsi: 4000, 5000, 6000, 7000. Jawaban: 6000)
        - "1 triwulan = ... bulan" (Opsi: 2, 3, 4, 6. Jawaban: 3)
        - "Keliling sisi 8 cm =" (Opsi: 16, 24, 32, 64. Jawaban: 32)


        --- Contoh Referensi Soal dari Dataset Saya (Sangat Penting untuk Diikuti) ---
        {context_samples_str if context_samples_str else "Tidak ada contoh yang tersedia. Buat soal berdasarkan topik dan level."}
        --- Akhir Contoh Referensi ---\n
        **Setiap soal yang Anda hasilkan WAJIB memiliki format JSON berikut:**
        {{
            "question": "Teks soal pertanyaan matematika yang jelas, singkat, dan langsung.",
            "options": ["Pilihan A (angka/nilai)", "Pilihan B (angka/nilai)", "Pilihan C (angka/nilai)", "Pilihan D (angka/nilai)"],
            "correct_answer": "Jawaban yang BENAR SECARA MATEMATIKA untuk 'question' yang Anda buat. Ini HARUS SAMA PERSIS dengan salah satu dari empat 'options' yang Anda berikan. Pastikan ini adalah nilai numerik atau string yang tepat, BUKAN KATA-KATA NON-NUMERIK JIKA SOALNYA NUMERIK."
        }}

        **FORMAT PENTING & ATURAN KETAT (BACA DAN IKUTI DENGAN SANGAT HATI-HATI):**
        1.  Output Anda **HARUS berupa JSON array yang VALID**, berisi **TEPAT {num_questions} objek soal**.
        2.  **JANGAN tambahkan teks lain di awal atau akhir** selain JSON array.
        3.  **JANGAN gunakan kurung kurawal ganda** seperti `{{` atau `}}` di output JSON Anda.
        4.  **Mulailah output Anda dengan karakter `[` dan akhiri dengan `]`** untuk memastikan ini adalah array JSON yang lengkap.
        5.  Setiap soal **WAJIB memiliki TEPAT 4 pilihan jawaban yang berbeda dan relevan**.
        6.  **PENTING SEKALI: Salah satu dari pilihan ini (options) HARUS menjadi `correct_answer` yang benar secara matematis.** Pastikan `correct_answer` adalah nilai yang sama persis dengan salah satu opsi.
        7.  **SANGAT PENTING: Opsi jawaban (Pilihan A, B, C, D) HARUS berupa angka atau nilai yang relevan secara matematis.** JANGAN PERNAH menyertakan kata-kata non-matematika atau konsep yang tidak terkait (misalnya, "kubus", "celcius", "lancip", "sejajar", "kerucut", "segitiga", "balok", "ruas", "batang", "lingkaran", "garis", "gambar") sebagai opsi jika soalnya adalah perhitungan atau konsep angka.
        8.  Untuk ekspresi matematika, gunakan angka biasa dan simbol operasi matematika standar (misal: `+`, `-`, `*`, `/`) atau kata-kata (misal: 'pecahan', 'pangkat') daripada notasi khusus (misal: $\\frac{{1}}{{2}}$, $10^2$). Contoh: '1 per 2' atau '1 dibagi 2' untuk pecahan, '10 pangkat 2' untuk eksponen.
        9.  **Pastikan soal-soal yang dihasilkan masuk akal, relevan secara matematika, dan jawabannya AKURAT 100%.**
        10. **PERIKSA KEMBALI JAWABAN ANDA SENDIRI** sebelum menghasilkan output. Pastikan perhitungan Anda benar.

        Hasilkan JSON array yang sama persis seperti contoh di atas, tetapi dengan {num_questions} soal baru yang sesuai topik dan tingkat kesulitan.
        """
        
        payload = {
            "model": model_name,
            "prompt": prompt_message,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1, # Menurunkan temperature lebih rendah lagi untuk konsistensi maksimal
                "top_p": 0.9 # Menambahkan top_p untuk fokus pada token probabilitas tinggi
            }
        }

        print(f"DEBUG: Mengirim payload ke Ollama: {json.dumps(payload, indent=2)}")

        response = requests.post(ollama_api_url, json=payload)
        response.raise_for_status()

        ollama_response_data = response.json()
        
        ai_response_content_str = ollama_response_data.get('response', '') 
        
        if not ai_response_content_str:
            raise ValueError("Model lokal tidak menghasilkan respons yang valid atau respons kosong.")

        print(f"DEBUG: Raw AI Response from Ollama (first 1000 chars):\n{ai_response_content_str[:1000]}\n...")

        extracted_json_str = fix_json_string(ai_response_content_str)
        
        print(f"DEBUG: Extracted and Fixed JSON String for parsing:\n{extracted_json_str}")

        if not extracted_json_str:
            raise ValueError(f"Model lokal menghasilkan respons tetapi tidak mengandung JSON yang valid setelah ekstraksi dan perbaikan. Respons mentah: {ai_response_content_str[:500]}...")
        
        try:
            generated_quiz_items = json.loads(extracted_json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gagal mengurai JSON dari respons AI bahkan setelah perbaikan: {e}. Respon mentah (setelah ekstraksi): {extracted_json_str[:500]}...")

        print(f"DEBUG: Parsed JSON Object: {json.dumps(generated_quiz_items, indent=2)}")
        
        final_quiz_list = []
        if isinstance(generated_quiz_items, list):
            final_quiz_list = generated_quiz_items
        elif isinstance(generated_quiz_items, dict):
            if 'question' in generated_quiz_items and \
               'options' in generated_quiz_items and \
               isinstance(generated_quiz_items.get('options'), list): 
                final_quiz_list = [generated_quiz_items]
            elif 'quiz' in generated_quiz_items and isinstance(generated_quiz_items['quiz'], list):
                final_quiz_list = generated_quiz_items['quiz']
            else:
                raise ValueError(f"Format JSON yang dihasilkan AI tidak sesuai. Diharapkan array, objek dengan kunci 'quiz', atau objek soal tunggal. Tipe root: {repr(type(generated_quiz_items))}, Kunci ditemukan: {list(generated_quiz_items.keys()) if isinstance(generated_quiz_items, dict) else 'N/A'}")
        else:
            raise ValueError(f"Format JSON yang dihasilkan AI tidak sesuai. Diharapkan array, objek dengan kunci 'quiz', atau objek soal tunggal. Tipe root: {repr(type(generated_quiz_items))}")

        validated_quiz_items = []
        for item in final_quiz_list:
            question_text = item.get('question')
            options_raw = item.get('options')
            correct_answer_text_ai = item.get('correct_answer')

            # Use the new calculate_correct_answer_and_options for robust processing
            final_question_text, final_options, final_correct_answer = \
                calculate_correct_answer_and_options(question_text, options_raw, correct_answer_text_ai)
            
            # Final validation before appending
            if (final_question_text and isinstance(final_question_text, str) and
                final_options and len(final_options) == 4 and 
                final_correct_answer and isinstance(final_correct_answer, str) and 
                str(final_correct_answer).strip() in final_options): 

                validated_quiz_items.append({
                    'question': str(final_question_text).strip(),
                    'options': final_options,
                    'correct_answer': str(final_correct_answer).strip()
                })
            else:
                missing_info = []
                if not final_question_text: missing_info.append('question')
                if not final_options or len(final_options) != 4: missing_info.append(f'options (invalid/not 4, current: {final_options})')
                if not final_correct_answer or not isinstance(final_correct_answer, str): missing_info.append('correct_answer (missing/invalid type)')
                elif final_correct_answer and str(final_correct_answer).strip() not in final_options: missing_info.append(f'correct_answer (not in options, current: {final_correct_answer})')
                
                print(f"Peringatan: Item kuis tidak valid atau tidak lengkap (Masalah: {', '.join(missing_info)}): {item}")


        if not validated_quiz_items:
            return jsonify({"error": "Model lokal menghasilkan JSON, namun tidak ada soal yang memenuhi format yang diharapkan (setiap soal harus memiliki 'question', array 'options' dengan TEPAT 4, dan 'correct_answer' yang sesuai dengan opsi)."}), 500

        print(f"DEBUG: Validated quiz items to be stored in quiz_taken_questions for quiz_history_id {quiz_history_id}: {json.dumps(validated_quiz_items, indent=2)}") 
        
        db = get_db()
        try:
            quiz_taken_cursor = db.cursor()
            for item in validated_quiz_items:
                quiz_taken_cursor.execute(
                    "INSERT INTO quiz_taken_questions (quiz_history_id, question_text, options_json, correct_answer, user_answer, is_correct) VALUES (%s, %s, %s, %s, %s, %s)",
                    (quiz_history_id, item['question'], json.dumps(item['options']), item['correct_answer'], None, None)
                )
            db.commit()
            print(f"DEBUG: Detail soal kuis AI disimpan ke quiz_taken_questions untuk quiz_history_id: {quiz_history_id}")
        except mysql.connector.Error as e:
            print(f"Error saving AI questions to quiz_taken_questions: {e}")
            db.rollback()
            return jsonify({"error": f"Gagal menyimpan detail soal AI: {str(e)}"}), 500
        finally:
            quiz_taken_cursor.close()

        return jsonify({"quiz": validated_quiz_items[:num_questions], "quiz_history_id": quiz_history_id}) 

    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_json = e.response.json()
                error_message = error_json.get('error', error_message)
            except json.JSONDecodeError:
                pass
        flash(f"Gagal memuat kuis: {error_message}. Pastikan Ollama berjalan dan model 'llama3' sudah diunduh jika menggunakan AI.", 'error')
        print(f"ERROR: RequestException di /api/generate_quiz_ai: {e}")
        return jsonify({"error": error_message}), 500
    except ValueError as e:
        print(f"ERROR: ValueError di /api/generate_quiz_ai: {e}")
        return jsonify({"error": f"Gagal menghasilkan kuis dengan model lokal: {str(e)}"}), 500
    except Exception as e:
        print(f"ERROR: Terjadi kesalahan tak terduga di api_generate_quiz_ai: {e}")
        return jsonify({"error": f"Terjadi kesalahan tak terduga saat menghasilkan kuis AI: {str(e)}"}), 500


@app.route('/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    quiz_history_id_raw = request.form.get('quiz_history_id')
    user_id = session.get('user_id')

    print(f"DEBUG: Raw request.form data received by submit_quiz: {request.form}")
    print(f"DEBUG: submit_quiz dipanggil. Menerima quiz_history_id_raw: '{quiz_history_id_raw}', dari user_id: {user_id}")

    quiz_history_id = None
    try:
        if quiz_history_id_raw:
            quiz_history_id = int(quiz_history_id_raw)
            print(f"DEBUG: Successfully converted quiz_history_id_raw '{quiz_history_id_raw}' to int: {quiz_history_id}")
        else:
            raise ValueError("quiz_history_id is missing or empty.")
    except (ValueError, TypeError) as e:
        flash("ID kuis tidak ditemukan. Tidak ada kuis yang sedang berlangsung atau sesi telah berakhir. (Error konversi ID)", 'error')
        print(f"ERROR: {e.__class__.__name__}: quiz_history_id tidak ditemukan atau tidak valid di submit_quiz (setelah konversi).")
        return redirect(url_for('dashboard'))

    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    quiz_meta = None
    quiz_taken_questions_db = []
    try:
        cursor.execute("SELECT user_id, level, topic, total_questions FROM quiz_history WHERE id = %s", (quiz_history_id,))
        quiz_meta = cursor.fetchone()
        
        if not quiz_meta or quiz_meta['user_id'] != user_id:
            flash("Kuis tidak ditemukan atau Anda tidak memiliki akses ke kuis ini.", 'error')
            print(f"ERROR: Kuis ID {quiz_history_id} tidak ditemukan atau bukan milik user {user_id}.")
            return redirect(url_for('dashboard'))

        cursor.execute("SELECT id, question_text, options_json, correct_answer FROM quiz_taken_questions WHERE quiz_history_id = %s ORDER BY id ASC", (quiz_history_id,))
        quiz_taken_questions_db = cursor.fetchall()
        
        print(f"DEBUG: Metadata kuis berhasil diambil untuk quiz_history_id {quiz_history_id}: {quiz_meta}")
        print(f"DEBUG: Ditemukan {len(quiz_taken_questions_db)} soal detail untuk quiz_history_id {quiz_history_id}.")

    except mysql.connector.Error as e:
        flash(f"Gagal mengambil data kuis dari database: {str(e)}", 'error')
        print(f"ERROR: Gagal mengambil data kuis dari database: {e}")
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()

    score = 0
    total_questions = quiz_meta['total_questions']
    results = []

    quiz_taken_cursor = db.cursor()
    try:
        for i, q_db in enumerate(quiz_taken_questions_db):
            user_answer = request.form.get(f'question_{i}')
            is_correct = (user_answer == q_db['correct_answer'])
            if is_correct:
                score += 1
            
            quiz_taken_cursor.execute(
                "UPDATE quiz_taken_questions SET user_answer = %s, is_correct = %s WHERE id = %s",
                (user_answer, is_correct, q_db['id'])
            )

            results.append({
                'question_id': q_db['id'],
                'question_text': q_db['question_text'],
                'user_answer': user_answer,
                'correct_answer': q_db['correct_answer'],
                'is_correct': is_correct,
                'options': json.loads(q_db['options_json'])
            })

        quiz_taken_cursor.execute(
            "UPDATE quiz_history SET score = %s WHERE id = %s",
            (score, quiz_history_id)
        )
        db.commit()
        print(f"DEBUG: Riwayat kuis ID {quiz_history_id} berhasil diperbarui dengan skor {score}/{total_questions}.")

    except mysql.connector.Error as e:
        flash(f'Gagal menyimpan hasil kuis: {str(e)}', 'error')
        print(f"ERROR: Gagal menyimpan hasil kuis: {e}")
        db.rollback()
    finally:
        quiz_taken_cursor.close()

    session.pop('temp_quiz_items', None)
    session.pop('current_quiz_id', None)

    return render_template('quiz_results.html', 
                           score=score, 
                           total_questions=total_questions, 
                           results=results, 
                           datetime=datetime)

@app.route('/view_quiz_history_details/<int:quiz_history_id>')
@login_required
def view_quiz_history_details(quiz_history_id):
    user_id = session.get('user_id')
    print(f"DEBUG: Meminta detail riwayat kuis ID {quiz_history_id} untuk user_id: {user_id}")

    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    quiz_meta = None
    results = []
    try:
        cursor.execute("SELECT level, topic, score, total_questions, timestamp, user_id FROM quiz_history WHERE id = %s", (quiz_history_id,))
        quiz_meta = cursor.fetchone()

        if not quiz_meta or quiz_meta['user_id'] != user_id:
            flash("Kuis tidak ditemukan atau Anda tidak memiliki akses ke riwayat ini.", 'error')
            print(f"ERROR: Detail kuis ID {quiz_history_id} tidak ditemukan atau bukan milik user {user_id}.")
            return redirect(url_for('dashboard'))
        
        cursor.execute("SELECT question_text, options_json, correct_answer, user_answer, is_correct FROM quiz_taken_questions WHERE quiz_history_id = %s ORDER BY id ASC", (quiz_history_id,))
        quiz_taken_questions_db = cursor.fetchall()

        for q in quiz_taken_questions_db:
            results.append({
                'question_text': q['question_text'],
                'user_answer': q['user_answer'],
                'correct_answer': q['correct_answer'],
                'is_correct': q['is_correct'],
                'options': json.loads(q['options_json'])
            })
        
        print(f"DEBUG: Detail kuis ID {quiz_history_id} berhasil diambil. Ditemukan {len(results)} soal.")

    except mysql.connector.Error as e:
        flash(f"Gagal mengambil detail riwayat kuis dari database: {str(e)}", 'error')
        print(f"ERROR: Gagal mengambil detail riwayat kuis dari database: {e}")
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()

    return render_template('quiz_results.html', 
                           score=quiz_meta['score'], 
                           total_questions=quiz_meta['total_questions'], 
                           results=results, 
                           datetime=datetime,
                           from_history=True)


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute("SELECT COUNT(*) as total_questions FROM quiz_questions")
    total_questions_db = cursor.fetchone()['total_questions']
    
    cursor.execute("SELECT level, COUNT(*) as count FROM quiz_questions GROUP BY level")
    questions_by_level = cursor.fetchall()
    
    cursor.execute("SELECT SUM(score) as total_score, SUM(total_questions) as total_possible FROM quiz_history")
    overall_performance = cursor.fetchone()
    
    cursor.execute("SELECT id, username, is_admin FROM users ORDER BY id ASC")
    users = cursor.fetchall()
    
    cursor.close()
    return render_template('admin/dashboard.html', 
                           total_users=total_users,
                           total_questions_db=total_questions_db,
                           questions_by_level=questions_by_level,
                           overall_performance=overall_performance,
                           users=users)

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    db = get_db()
    
    if user_id == session['user_id']:
        flash('Anda tidak bisa mengubah status admin Anda sendiri.', 'error')
        return redirect(url_for('admin_dashboard'))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
    user_to_toggle = cursor.fetchone()

    if not user_to_toggle:
        flash('Pengguna tidak ditemukan.', 'error')
    else:
        new_status = not bool(user_to_toggle['is_admin'])
        try:
            cursor.execute("UPDATE users SET is_admin = %s WHERE id = %s", (new_status, user_id))
            db.commit()
            if new_status:
                flash(f'Pengguna ID {user_id} berhasil dijadikan admin.', 'success')
            else:
                flash(f'Pengguna ID {user_id} berhasil dinon-aktifkan dari admin.', 'success')
        except mysql.connector.Error as e:
            flash(f'Gagal mengubah status admin: {str(e)}', 'error')
            db.rollback()
        finally:
            cursor.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    db = get_db()

    if user_id == session['user_id']:
        flash('Anda tidak bisa menghapus akun Anda sendiri.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM quiz_history WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM quiz_taken_questions WHERE quiz_history_id IN (SELECT id FROM quiz_history WHERE user_id = %s)", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()
        flash(f'Pengguna ID {user_id} dan riwayat kuisnya berhasil dihapus.', 'success')
    except mysql.connector.Error as e:
        flash(f'Gagal menghapus pengguna: {str(e)}', 'error')
        db.rollback()
    finally:
        cursor.close()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/questions')
@admin_required
def admin_questions():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT id, level, question, correct_answer FROM quiz_questions ORDER BY level, id')
    questions = cursor.fetchall()
    cursor.close()
    return render_template('admin/questions.html', questions=questions)

@app.route('/admin/add_question', methods=['GET', 'POST'])
@admin_required
def add_question():
    if request.method == 'POST':
        level = request.form['level']
        question = request.form['question']
        option_a = request.form['option_a']
        option_b = request.form['option_b']
        option_c = request.form['option_c']
        option_d = request.form['option_d']
        correct_answer = request.form['correct_answer']

        options_list = [option_a, option_b, option_c, option_d]

        if correct_answer not in options_list:
            flash('Jawaban Benar harus persis sama dengan salah satu Pilihan A, B, C, atau D.', 'error')
            return render_template('admin/add_question.html')

        options_json = json.dumps(options_list)
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO quiz_questions (level, question, options, correct_answer) VALUES (%s, %s, %s, %s)',
                           (level, question, options_json, correct_answer))
            db.commit()
            flash('Soal kuis berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_questions'))
        except mysql.connector.Error as e:
            flash(f'Gagal menambahkan soal: {str(e)}', 'error')
            db.rollback()
        finally:
            cursor.close()
    return render_template('admin/add_question.html')

@app.route('/admin/edit_question/<int:question_id>', methods=['GET', 'POST'])
@admin_required
def edit_question(question_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM quiz_questions WHERE id = %s', (question_id,))
    question = cursor.fetchone()
    cursor.close()

    if not question:
        flash('Soal tidak ditemukan.', 'error')
        return redirect(url_for('admin_questions'))

    if request.method == 'POST':
        level = request.form['level']
        question_text = request.form['question']
        option_a = request.form['option_a']
        option_b = request.form['option_b']
        option_c = request.form['option_c']
        option_d = request.form['option_d']
        correct_answer = request.form['correct_answer']

        options_list = [option_a, option_b, option_c, option_d]

        if correct_answer not in options_list:
            flash('Jawaban Benar harus persis sama dengan salah satu Pilihan A, B, C, atau D.', 'error')
            question_data = {
                'id': question_id,
                'level': level,
                'question': question_text,
                'options': json.dumps(options_list),
                'correct_answer': correct_answer
            }
            return render_template('admin/edit_question.html', question=question_data, options=options_list)

        options_json = json.dumps(options_list)
        db_conn = get_db()
        cursor = db_conn.cursor()
        try:
            cursor.execute('UPDATE quiz_questions SET level = %s, question = %s, options = %s, correct_answer = %s WHERE id = %s',
                           (level, question_text, options_json, correct_answer, question_id))
            db_conn.commit()
            flash('Soal kuis berhasil diperbarui!', 'success')
            return redirect(url_for('admin_questions'))
        except mysql.connector.Error as e:
            flash(f'Gagal memperbarui soal: {str(e)}', 'error')
            db_conn.rollback()
        finally:
            cursor.close()
    else:
        options = json.loads(question['options'])
        return render_template('admin/edit_question.html', question=question, options=options)

@app.route('/admin/delete_question/<int:question_id>', methods=['POST'])
@admin_required
def delete_question(question_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('DELETE FROM quiz_questions WHERE id = %s', (question_id,))
        db.commit()
        flash('Soal kuis berhasil dihapus!', 'success')
    except mysql.connector.Error as e:
        flash(f'Gagal menghapus soal: {str(e)}', 'error')
        db.rollback()
    finally:
        cursor.close()
    return redirect(url_for('admin_questions'))

@app.route('/admin/datasets', methods=['GET', 'POST'])
@admin_required
def admin_datasets():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM uploaded_datasets ORDER BY upload_date DESC')
    uploaded_datasets_db = cursor.fetchall()
    cursor.close()

    if request.method == 'POST':
        if 'dataset_file' not in request.files:
            flash('Tidak ada bagian file.', 'error')
            return render_template('admin/datasets.html', default_datasets=DATASETS, uploaded_datasets=uploaded_datasets_db)
        
        file = request.files['dataset_file']
        
        if file.filename == '':
            flash('Tidak ada file terpilih.', 'error')
            return render_template('admin/datasets.html', default_datasets=DATASETS, uploaded_datasets=uploaded_datasets_db)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            db_conn = get_db()
            check_cursor = db_conn.cursor()
            check_cursor.execute("SELECT COUNT(*) FROM uploaded_datasets WHERE filename = %s", (filename,))
            if check_cursor.fetchone()[0] > 0:
                flash(f'File "{filename}" sudah ada di database. Harap ganti nama atau hapus yang lama.', 'error')
                check_cursor.close()
                return render_template('admin/datasets.html', default_datasets=DATASETS, uploaded_datasets=uploaded_datasets_db)
            check_cursor.close()

            try:
                file.save(filepath)
                file_size = os.path.getsize(filepath)
                upload_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                db_conn = get_db()
                insert_cursor = db_conn.cursor()
                insert_cursor.execute('INSERT INTO uploaded_datasets (filename, filepath, size, upload_date) VALUES (%s, %s, %s, %s)',
                                       (filename, filepath, file_size, upload_date))
                db_conn.commit()
                insert_cursor.close()

                inferred_level = filename.split('_')[0].upper() if '_' in filename else None
                imported_count = import_questions_from_csv_to_db(filepath, level_context=inferred_level)
                
                if imported_count > 0:
                    flash(f'Dataset "{filename}" berhasil diunggah dan {imported_count} soal berhasil diimpor!', 'success')
                else:
                    flash(f'Dataset "{filename}" diunggah, tetapi tidak ada soal valid yang diimpor. Periksa format CSV.', 'warning')

            except mysql.connector.Error as e:
                flash(f'Gagal mengunggah dataset ke database: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
                if db_conn:
                    db_conn.rollback()
            except Exception as e:
                flash(f'Terjadi kesalahan tak terduga saat mengunggah dataset: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Format file tidak diizinkan. Hanya file CSV.', 'error')
            
    return render_template('admin/datasets.html', 
                           default_datasets=DATASETS, 
                           uploaded_datasets=uploaded_datasets_db)

@app.route('/admin/delete_dataset/<path:filename>', methods=['POST'])
@admin_required
def delete_dataset(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM uploaded_datasets WHERE filename = %s', (filename,))
    dataset_record = cursor.fetchone()
    cursor.close()

    if not dataset_record:
        flash('Dataset tidak ditemukan di database.', 'error')
        return redirect(url_for('admin_datasets'))

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        
        db_conn = get_db()
        delete_cursor = db_conn.cursor()
        delete_cursor.execute('DELETE FROM uploaded_datasets WHERE filename = %s', (filename,))
        db_conn.commit()
        delete_cursor.close()
        flash(f'Dataset "{filename}" berhasil dihapus.', 'success')
    except mysql.connector.Error as e:
        flash(f'Gagal menghapus dataset "{filename}" dari database: {str(e)}', 'error')
        db_conn.rollback()
    except Exception as e:
        flash(f'Terjadi kesalahan tak terduga saat menghapus dataset: {str(e)}', 'error')
        
    return redirect(url_for('admin_datasets'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)