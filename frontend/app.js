const API_URL = '/api';

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusBlock = document.getElementById('status-block');
const statusText = document.getElementById('status');
const downloadLink = document.getElementById('download-link');
const filenameDisplay = document.getElementById('filename-display'); 

let currentTaskId = null;
let currentFileType = null;

// --- ЛОГИКА ОТКРЫТИЯ/ЗАКРЫТИЯ МЕНЮ ---
const dropdownToggles = document.querySelectorAll('.dropdown-toggle');

dropdownToggles.forEach(toggle => {
    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const menu = toggle.nextElementSibling;
        
        document.querySelectorAll('.dropdown-menu.show').forEach(openMenu => {
            if (openMenu !== menu) openMenu.classList.remove('show');
        });

        menu.classList.toggle('show');
    });
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('.dropdown')) {
        document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
        });
    }
});

// Клик по зоне -> выбор файла
dropZone.addEventListener('click', () => fileInput.click());

// Drag & Drop
dropZone.addEventListener('dragover', (e) => e.preventDefault());
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) uploadFile(e.target.files[0]);
});

// Загрузка файла
async function uploadFile(file) {
    if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) {
        alert('Ошибка: Пожалуйста, загрузите изображение или видео!');
        return; 
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData });
        
        if (!res.ok) {
            throw new Error('Ошибка сервера');
        }

        const data = await res.json();
        
        currentTaskId = data.task_id;
        currentFileType = data.file_type;
        
        document.getElementById('upload-block').classList.add('hidden');
        document.getElementById('preview-section').classList.remove('hidden');
        
        if (filenameDisplay) {
            filenameDisplay.textContent = data.filename;
        }

        const mediaContainer = document.getElementById('media-container');
        const existingMedia = mediaContainer.querySelector('img, video');
        if (existingMedia) existingMedia.remove();

        const fileURL = URL.createObjectURL(file);

        if (data.file_type === 'image') {
            const img = document.createElement('img');
            img.src = fileURL;
            mediaContainer.appendChild(img);
            document.getElementById('photo-btns').classList.remove('hidden');
        } else {
            const video = document.createElement('video');
            video.src = fileURL;
            video.controls = true;
            mediaContainer.appendChild(video);
            document.getElementById('video-btns').classList.remove('hidden');
        }
        
    } catch (err) {
        alert('Ошибка загрузки: ' + err.message);
    }
}

// Отправка команды на обработку
async function sendAction(action, params = {}) {
    document.getElementById('preview-section').classList.add('hidden');
    statusBlock.classList.remove('hidden');
    statusText.textContent = 'Обработка...';

    try {
        const res = await fetch(`${API_URL}/process`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: currentTaskId,
                action: action,
                params: params
            })
        });

        if (res.ok) {
            checkStatus();
        }
    } catch (err) {
        alert('Ошибка: ' + err);
    }
}

// --- ОБРАБОТКА КНОПОК ФОТО ---

// 1. Меню "Шакал"
document.querySelectorAll('.dropdown-menu button[data-quality]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation(); 
        const quality = btn.getAttribute('data-quality'); 
        sendAction('shakal', { quality: parseInt(quality) }); 
    });
});

// 2. Меню "Ресайз"
document.getElementById('apply-resize').addEventListener('click', (e) => {
    e.stopPropagation();
    const width = document.getElementById('resize-width').value;
    const height = document.getElementById('resize-height').value;
    if (!width || !height) { alert('Введите ширину и высоту!'); return; }
    sendAction('resize', { width: parseInt(width), height: parseInt(height) });
});

// 3. Меню "Яркость"
const brightnessRange = document.getElementById('brightness-range');
const brightnessValue = document.getElementById('brightness-value');
brightnessRange.addEventListener('input', () => {
    brightnessValue.textContent = brightnessRange.value;
});
document.getElementById('apply-brightness').addEventListener('click', (e) => {
    e.stopPropagation();
    const factor = parseInt(brightnessRange.value) / 100; 
    sendAction('filter', { brightness: factor });
});

// 4. Меню "Резкость"
const sharpnessRange = document.getElementById('sharpness-range');
const sharpnessValue = document.getElementById('sharpness-value');
sharpnessRange.addEventListener('input', () => {
    sharpnessValue.textContent = sharpnessRange.value;
});
document.getElementById('apply-sharpness').addEventListener('click', (e) => {
    e.stopPropagation();
    const factor = parseInt(sharpnessRange.value) / 100; 
    sendAction('sharpness', { factor: factor });
});

// 5. Меню "Контраст"
const contrastRange = document.getElementById('contrast-range');
const contrastValue = document.getElementById('contrast-value');
contrastRange.addEventListener('input', () => {
    contrastValue.textContent = contrastRange.value;
});
document.getElementById('apply-contrast').addEventListener('click', (e) => {
    e.stopPropagation();
    const factor = parseInt(contrastRange.value) / 100; 
    sendAction('contrast', { factor: factor });
});

// --- ОБРАБОТКА КНОПОК ВИДЕО ---

// 1. Меню "Шакал" для видео
document.querySelectorAll('#video-btns .dropdown-menu button[data-vquality]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation(); 
        const quality = btn.getAttribute('data-vquality'); 
        sendAction('shakal_video', { quality: parseInt(quality) }); 
    });
});

// 2. Кнопка "Сжать"
document.querySelector('.compress-btn').addEventListener('click', () => {
    sendAction('compress', {});
});

// 3. Меню "Скорость" для видео
const speedRange = document.getElementById('speed-range');
const speedValue = document.getElementById('speed-value');

// Обновляем цифру на экране, когда двигаем ползунок
speedRange.addEventListener('input', () => {
    // Округляем до одного знака после запятой (например, 1.5)
    speedValue.textContent = parseFloat(speedRange.value).toFixed(1);
});

document.getElementById('apply-speed').addEventListener('click', (e) => {
    e.stopPropagation();
    const speedFactor = parseFloat(speedRange.value);
    
    // Отправляем action='change_speed' и параметр speed
    sendAction('change_speed', { speed: speedFactor });
});

// Проверка статуса
function checkStatus() {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`${API_URL}/status/${currentTaskId}`);
            const data = await res.json();

            if (data.status === 'completed') {
                clearInterval(interval);
                statusText.textContent = 'Готово!';
                
                const downloadUrl = `/api/download/${currentTaskId}`;
                downloadLink.href = downloadUrl;

                // Показываем превью (картинка или видео)
                if (currentFileType === 'image') {
                    const img = document.getElementById('result-image');
                    img.src = downloadUrl;
                    img.classList.remove('hidden');
                } else if (currentFileType === 'video') {
                    const video = document.getElementById('result-video');
                    video.src = downloadUrl;
                    video.classList.remove('hidden');
                }
                document.getElementById('result-preview-container').classList.remove('hidden');

                // !!! ВАЖНО: Показываем кнопки скачивания и сброса
                downloadLink.classList.remove('hidden');
                document.getElementById('reset-btn').classList.remove('hidden');
            }
        } catch (err) { 
            console.log('Ждем...');
        }
    }, 2000);
}

// Кнопка "Начать заново"
document.getElementById('reset-btn').addEventListener('click', () => {
    window.location.reload();
});