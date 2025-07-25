// static/js/script.js

// Fungsi yang dipanggil saat tombol "Generate Kuis" di dashboard ditekan
// Parameter 'type' akan menentukan apakah kuis manual atau AI
function generateQuiz(type) {
    let url = '';
    
    if (type === 'manual') {
        const level = document.getElementById('level-select').value; // Menggunakan ID yang benar
        const numQuestions = parseInt(document.getElementById('num-questions').value); // Menggunakan ID yang benar
        if (isNaN(numQuestions) || numQuestions < 1 || numQuestions > 20) {
            alert("Jumlah soal untuk kuis manual harus antara 1 dan 20.");
            console.error("DEBUG JS: Validasi kuis manual gagal: Jumlah soal tidak valid.");
            return;
        }
        url = `/quiz?type=manual&level=${level}&num_questions=${numQuestions}`;
    } else if (type === 'ai') {
        const topic = document.getElementById('ai-topic').value; // Menggunakan ID yang benar
        const numQuestions = parseInt(document.getElementById('ai-num-questions').value); // Menggunakan ID yang benar
        const levelContext = document.getElementById('ai-context-level').value; // Menggunakan ID yang benar

        if (!topic.trim()) {
            alert("Topik untuk kuis AI tidak boleh kosong.");
            console.error("DEBUG JS: Validasi kuis AI gagal: Topik kosong.");
            return;
        }
        if (isNaN(numQuestions) || numQuestions < 1 || numQuestions > 10) {
            alert("Jumlah soal untuk kuis AI harus antara 1 dan 10.");
            console.error("DEBUG JS: Validasi kuis AI gagal: Jumlah soal tidak valid.");
            return;
        }
        url = `/quiz?type=ai&topic=${encodeURIComponent(topic)}&num_questions=${numQuestions}&level_context=${levelContext}`;
    } else {
        alert("Tipe kuis tidak valid.");
        console.error("DEBUG JS: Tipe kuis tidak valid.");
        return;
    }
    console.log(`DEBUG JS: Mengarahkan ke URL kuis: ${url}`);
    window.location.href = url;
}

// Fungsi untuk memuat dan menampilkan kuis (akan dipanggil oleh quiz.html)
async function loadQuizContent() {
    const quizDisplayArea = document.getElementById('quiz-container');
    if (!quizDisplayArea) {
        console.error("ERROR JS: Elemen #quiz-container tidak ditemukan.");
        return;
    }
    quizDisplayArea.style.display = 'block'; // Pastikan kontainer kuis terlihat

    const urlParams = new URLSearchParams(window.location.search);
    const quizType = urlParams.get('type');
    const numQuestions = parseInt(urlParams.get('num_questions'));

    let requestBody = {};
    let apiUrl = '';

    console.log('DEBUG JS: --- loadQuizContent Init ---');
    console.log('DEBUG JS: URL Parameters:', window.location.search);
    console.log('DEBUG JS: Parsed quizType:', quizType);
    console.log('DEBUG JS: Parsed numQuestions:', numQuestions);

    if (quizType === 'manual') {
        const level = urlParams.get('level');
        if (!level || isNaN(numQuestions) || numQuestions < 1 || numQuestions > 20) {
            quizDisplayArea.innerHTML = `
                <p class="error-message status-message">Parameter kuis manual tidak valid. Kembali ke <a href="/dashboard">Dashboard</a>.</p>
            `;
            console.error("ERROR JS: Kuis Manual: Parameter tidak valid terdeteksi.");
            return;
        }
        requestBody = { level: level, num_questions: numQuestions };
        apiUrl = '/api/generate_quiz';
        quizDisplayArea.innerHTML = `
            <p class="loading-message status-message">
                <span class="spinner"></span> Mempersiapkan kuis manual untuk level ${level}...
            </p>
        `;
        console.log(`DEBUG JS: Mempersiapkan permintaan API untuk kuis manual. Level: ${level}, Soal: ${numQuestions}`);
    } else if (quizType === 'ai') {
        const topic = urlParams.get('topic');
        const levelContext = urlParams.get('level_context');

        if (!topic || isNaN(numQuestions) || numQuestions < 1 || numQuestions > 10 || !levelContext) {
            quizDisplayArea.innerHTML = `
                <p class="error-message status-message">Parameter kuis AI tidak valid. Pastikan Topik, Jumlah Soal, dan Gaya Soal Mirip Dataset dipilih di <a href="/dashboard">Dashboard</a>.</p>
            `;
            console.error("ERROR JS: Kuis AI: Parameter tidak valid terdeteksi.");
            return;
        }
        requestBody = { topic: decodeURIComponent(topic), num_questions: numQuestions, level_context: levelContext };
        apiUrl = '/api/generate_quiz_ai';
        quizDisplayArea.innerHTML = `
            <p class="loading-message status-message">
                <span class="spinner"></span> Mempersiapkan kuis AI tentang "${decodeURIComponent(topic)}", dengan gaya ${levelContext}...
                <br><small>Ini mungkin membutuhkan waktu beberapa detik.</small>
            </p>
        `;
        console.log(`DEBUG JS: Mempersiapkan permintaan API untuk kuis AI. Topik: ${decodeURIComponent(topic)}, Level Konteks: ${levelContext}, Soal: ${numQuestions}`);
    } else {
        quizDisplayArea.innerHTML = `
            <p class="error-message status-message">Tipe kuis tidak valid. Kembali ke <a href="/dashboard">Dashboard</a>.</p>
        `;
        console.error("ERROR JS: Tipe kuis tidak valid terdeteksi.");
        return;
    }

    try {
        console.log(`DEBUG JS: Mengirim permintaan fetch ke: ${apiUrl}`);
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error("ERROR JS: Respon API tidak OK:", errorData);
            throw new Error(errorData.error || 'Terjadi kesalahan saat membuat kuis.');
        }

        const data = await response.json();
        console.log("DEBUG JS: Data respon API berhasil diterima:", data);

        quizDisplayArea.innerHTML = ''; // Bersihkan konten sebelumnya

        if (data.quiz && data.quiz.length > 0 && data.quiz_history_id) {
            console.log(`DEBUG JS: Kuis dan quiz_history_id (${data.quiz_history_id}) diterima. Membangun formulir kuis.`);
            const quizForm = document.createElement('form');
            quizForm.id = 'quizForm';
            quizForm.action = '/submit_quiz'; 
            quizForm.method = 'POST';

            // PENTING: Tambahkan hidden input untuk quiz_history_id
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = 'quiz_history_id';
            hiddenInput.value = data.quiz_history_id; // data.quiz_history_id comes from API response
            quizForm.appendChild(hiddenInput);
            console.log(`DEBUG JS: Hidden input quiz_history_id ditambahkan ke form dengan value: ${hiddenInput.value}`);


            data.quiz.forEach((item, index) => {
                const questionCard = document.createElement('div');
                questionCard.className = 'question-card'; // Menggunakan kelas yang sudah ada di style.css
                
                let optionsHtml = '<ul class="options-list">'; // Menggunakan kelas yang sudah ada di style.css
                const optionsToShuffle = Array.isArray(item.options) && item.options.length >= 4 ? [...item.options] : [item.correct_answer, "Pilihan B", "Pilihan C", "Pilihan D"];
                const shuffledOptions = optionsToShuffle.sort(() => Math.random() - 0.5);

                shuffledOptions.forEach(option => {
                    // Menggunakan btoa() untuk meng-encode option agar ID HTML valid
                    const encodedOption = btoa(option).replace(/=/g, ''); 
                    optionsHtml += `
                        <li>
                            <input type="radio" id="q${index}_option_${encodedOption}" name="question_${index}" value="${option}" required>
                            <label for="q${index}_option_${encodedOption}">${option}</label>
                        </li>
                    `;
                });
                optionsHtml += '</ul>';

                questionCard.innerHTML = `
                    <h3>${index + 1}. ${item.question}</h3>
                    ${optionsHtml}
                    <div class="feedback-area" style="display:none;"></div>
                `;
                quizForm.appendChild(questionCard);
                console.log(`DEBUG JS: Soal ${index + 1} ditambahkan ke formulir.`);
            });

            const submitButton = document.createElement('button');
            submitButton.type = 'submit';
            submitButton.className = 'btn-primary'; // Menggunakan kelas yang sudah ada di style.css
            submitButton.textContent = 'Selesai Kuis';
            submitButton.style.marginTop = '30px';
            quizForm.appendChild(submitButton);
            console.log("DEBUG JS: Tombol submit ditambahkan.");

            quizDisplayArea.appendChild(quizForm);
            
        } else {
            quizDisplayArea.innerHTML = `
                <p class="error-message status-message">
                    Tidak ada soal yang tersedia untuk kriteria ini atau ID riwayat kuis tidak ditemukan. Coba topik, level, atau jumlah soal lain.
                </p>
            `;
            console.warn("DEBUG JS: Tidak ada kuis yang diterima atau quiz_history_id hilang.");
        }
    } catch (error) {
        console.error('ERROR JS: Gagal memuat kuis:', error);
        quizDisplayArea.innerHTML = `
            <p class="error-message status-message">
                Error: Gagal memuat kuis. ${error.message}
            </p>
        `;
    }
}


// Event listener utama yang akan dijalankan setelah DOM dimuat
document.addEventListener('DOMContentLoaded', function() {
    console.log("DEBUG JS: DOMContentLoaded event fired.");

    // Logika untuk tombol "Cetak ke PDF" di halaman quiz_results.html
    const printPdfBtn = document.getElementById('printPdfBtn');
    if (printPdfBtn) {
        printPdfBtn.addEventListener('click', function() {
            console.log("DEBUG JS: Tombol Cetak ke PDF diklik.");
            const element = document.getElementById('quiz-results-pdf-content'); // Ambil elemen yang ingin dicetak

            const options = {
                margin: 10,
                filename: 'hasil_kuis_GeneratorKu.pdf',
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2 }, 
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            };

            if (typeof html2pdf !== 'undefined') {
                html2pdf().set(options).from(element).save();
                console.log("DEBUG JS: html2pdf.js dipanggil untuk menyimpan PDF.");
            } else {
                console.error("ERROR JS: Library html2pdf.js tidak dimuat.");
                alert("Gagal memuat fungsi cetak PDF. Mohon refresh halaman.");
            }
        });
    }

    // Tidak ada quizTypeSelect, manualOptionsDiv, aiOptionsDiv di dashboard.html versi pengguna ini.
    // Kode ini tidak lagi relevan dengan dashboard.html yang diberikan pengguna.

    // Event listener for starting the quiz from dashboard
    // Ini sekarang terhubung langsung ke onclick="generateQuiz(...)" di dashboard.html
    // const startQuizBtn = document.getElementById('start-quiz-btn');
    // if (startQuizBtn) {
    //     startQuizBtn.addEventListener('click', function() {
    //         console.log("DEBUG JS: Tombol 'Mulai Kuis' diklik.");
    //         // generateQuiz(quizTypeSelect.value); // quizTypeSelect is not defined here
    //     });
    // }

    // Panggil loadQuizContent() hanya jika kita berada di halaman /quiz
    if (window.location.pathname === '/quiz') {
        console.log("DEBUG JS: Berada di halaman /quiz. Memanggil loadQuizContent().");
        loadQuizContent();
    }

    // Auto-hide flash messages after a few seconds
    const flashMessages = document.querySelectorAll('.flashes .alert');
    flashMessages.forEach(function(msg) {
        console.log("DEBUG JS: Mengatur auto-hide untuk flash message.");
        setTimeout(function() {
            msg.classList.add('fade');
            msg.classList.remove('show');
            msg.addEventListener('transitionend', function() {
                msg.remove();
                console.log("DEBUG JS: Flash message dihapus.");
            });
        }, 5000); // Hide after 5 seconds
    });
});
