-- schema.sql
-- File ini berisi perintah SQL untuk membuat tabel database Anda di MySQL.

-- Hapus tabel jika sudah ada untuk memastikan skema bersih saat inisialisasi
-- Gunakan IF EXISTS untuk menghindari error jika tabel belum ada
DROP TABLE IF EXISTS quiz_taken_questions;
DROP TABLE IF EXISTS quiz_history;
DROP TABLE IF EXISTS quiz_questions;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS uploaded_datasets;

-- Tabel untuk menyimpan informasi pengguna
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    is_admin TINYINT(1) DEFAULT 0
);

-- Tabel untuk menyimpan soal-soal kuis yang dikelola admin
CREATE TABLE quiz_questions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    level VARCHAR(10) NOT NULL,
    question TEXT NOT NULL,
    options TEXT NOT NULL,
    correct_answer VARCHAR(255) NOT NULL
);

-- Tabel untuk menyimpan riwayat kuis pengguna (summary)
CREATE TABLE quiz_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    level VARCHAR(50) NOT NULL,
    topic VARCHAR(255) DEFAULT 'Umum',
    score INT NOT NULL,
    total_questions INT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabel baru untuk menyimpan detail setiap soal kuis yang diambil
CREATE TABLE quiz_taken_questions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    quiz_history_id INT NOT NULL,
    question_text TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    user_answer TEXT,
    is_correct BOOLEAN,
    FOREIGN KEY (quiz_history_id) REFERENCES quiz_history(id) ON DELETE CASCADE
);

-- Tabel untuk melacak dataset yang diunggah oleh admin
CREATE TABLE uploaded_datasets (
    id INT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) UNIQUE NOT NULL,
    filepath VARCHAR(512) NOT NULL,
    size BIGINT NOT NULL,
    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP
);
