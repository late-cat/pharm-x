// ===== DOM Elements =====
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const preview = document.getElementById('preview');
const previewImage = document.getElementById('previewImage');
const removeBtn = document.getElementById('removeBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const loading = document.getElementById('loading');
const error = document.getElementById('error');
const errorText = document.getElementById('errorText');
const errorDetail = document.getElementById('errorDetail');
const results = document.getElementById('results');
const prescriptionInfo = document.getElementById('prescriptionInfo');
const medicineList = document.getElementById('medicineList');
const medicineCount = document.getElementById('medicineCount');
const scheduleGrid = document.getElementById('scheduleGrid');
const newAnalysisBtn = document.getElementById('newAnalysisBtn');

let selectedFile = null;

// ===== Upload Zone Handlers =====

uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        handleFile(file);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files[0]) {
        handleFile(e.target.files[0]);
    }
});

removeBtn.addEventListener('click', () => {
    resetUpload();
});

analyzeBtn.addEventListener('click', () => {
    analyzePrescription();
});

newAnalysisBtn.addEventListener('click', () => {
    resetAll();
});

// ===== File Handling =====

function handleFile(file) {
    selectedFile = file;

    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        preview.classList.add('show');
        uploadZone.classList.add('has-file');
        uploadZone.querySelector('.upload-zone__text').textContent = file.name;
        uploadZone.querySelector('.upload-zone__hint').textContent = formatFileSize(file.size);
        analyzeBtn.classList.add('show');
    };
    reader.readAsDataURL(file);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function resetUpload() {
    selectedFile = null;
    fileInput.value = '';
    preview.classList.remove('show');
    uploadZone.classList.remove('has-file');
    uploadZone.querySelector('.upload-zone__text').textContent = 'Drop your prescription image here';
    uploadZone.querySelector('.upload-zone__hint').textContent = 'or click to browse • JPG, PNG, WebP • Max 10MB';
    analyzeBtn.classList.remove('show');
}

function resetAll() {
    resetUpload();
    results.classList.remove('show');
    error.classList.remove('show');
    loading.classList.remove('show');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== API Call =====

async function analyzePrescription() {
    if (!selectedFile) return;

    // Show loading, hide others
    loading.classList.add('show');
    error.classList.remove('show');
    results.classList.remove('show');
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = '⏳ Analyzing...';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Analysis failed');
        }

        const data = await response.json();
        renderResults(data);

    } catch (err) {
        showError(err.message);
    } finally {
        loading.classList.remove('show');
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = '🔍 Analyze Prescription';
    }
}

// ===== Render Results =====

function renderResults(data) {
    // Prescription info
    renderPrescriptionInfo(data.prescription_info);

    // Medicine cards
    renderMedicineCards(data.medicines);

    // Daily schedule
    renderSchedule(data.daily_schedule);

    // Show results
    results.classList.add('show');

    // Scroll to results
    setTimeout(() => {
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function renderPrescriptionInfo(info) {
    if (!info) {
        prescriptionInfo.classList.remove('show');
        return;
    }

    const hasInfo = info.doctor_name || info.patient_name || info.date || info.diagnosis;

    if (!hasInfo) {
        prescriptionInfo.classList.remove('show');
        return;
    }

    let html = '';

    if (info.doctor_name) {
        html += `<div class="prescription-info__item">
            <span class="prescription-info__label">👨‍⚕️ Doctor:</span>
            <span class="prescription-info__value">${escapeHtml(info.doctor_name)}</span>
        </div>`;
    }
    if (info.patient_name) {
        html += `<div class="prescription-info__item">
            <span class="prescription-info__label">🧑 Patient:</span>
            <span class="prescription-info__value">${escapeHtml(info.patient_name)}</span>
        </div>`;
    }
    if (info.date) {
        html += `<div class="prescription-info__item">
            <span class="prescription-info__label">📅 Date:</span>
            <span class="prescription-info__value">${escapeHtml(info.date)}</span>
        </div>`;
    }
    if (info.diagnosis) {
        html += `<div class="prescription-info__item">
            <span class="prescription-info__label">🩺 Diagnosis:</span>
            <span class="prescription-info__value">${escapeHtml(info.diagnosis)}</span>
        </div>`;
    }

    prescriptionInfo.innerHTML = html;
    prescriptionInfo.classList.add('show');
}

function renderMedicineCards(medicines) {
    if (!medicines || medicines.length === 0) {
        medicineList.innerHTML = '<p style="text-align:center;color:var(--text-muted);">No medicines detected</p>';
        medicineCount.textContent = '0';
        return;
    }

    medicineCount.textContent = medicines.length;

    let html = '';
    medicines.forEach((med, index) => {
        html += createMedicineCard(med, index + 1);
    });

    medicineList.innerHTML = html;
}

function createMedicineCard(med, number) {
    const warningHtml = med.warnings ? `
        <div class="medicine-card__warning">
            <span class="medicine-card__warning-icon">⚠️</span>
            <span>${escapeHtml(med.warnings)}</span>
        </div>` : '';

    const matchInfo = med.match_score && med.match_score < 100
        ? `<span style="font-size:11px;color:var(--text-muted);margin-left:6px;">(${med.match_score}% match)</span>`
        : '';

    const hasExactPrice = !!med.price;
    const priceDisplay = hasExactPrice ? `₹${escapeHtml(med.price)}` : (med.estimated_price ? escapeHtml(med.estimated_price) : 'N/A');
    const priceClass = hasExactPrice ? ' medicine-card__detail-value--highlight' : ' medicine-card__detail-value--estimate';
    const priceLabel = hasExactPrice ? '💰 Price (MRP)' : '💰 Estimated Price';
    
    const priceHtml = `
        <div class="medicine-card__detail">
            <span class="medicine-card__detail-label">${priceLabel}</span>
            <span class="medicine-card__detail-value${priceClass}">${priceDisplay}</span>
        </div>`;
        
    const availabilityHtml = med.available_on ? `
        <div class="medicine-card__detail medicine-card__detail--full">
            <span class="medicine-card__detail-label">🛒 Available On</span>
            <span class="medicine-card__detail-value">${escapeHtml(med.available_on)}</span>
        </div>` : '';
        
    const manufacturerHtml = med.manufacturer ? `
        <div class="medicine-card__detail medicine-card__detail--full">
            <span class="medicine-card__detail-label">🏭 Manufacturer</span>
            <span class="medicine-card__detail-value">${escapeHtml(med.manufacturer)}</span>
        </div>` : '';

    return `
    <div class="medicine-card">
        <div class="medicine-card__header">
            <div>
                <div style="display:flex;align-items:center;">
                    <span class="medicine-card__number">${number}</span>
                    <span class="medicine-card__name">${escapeHtml(med.name)}</span>
                    ${matchInfo}
                </div>
                ${med.generic_name ? `<div class="medicine-card__generic">${escapeHtml(med.generic_name)}</div>` : ''}
            </div>
            ${med.type ? `<span class="medicine-card__type-badge">${escapeHtml(med.type)}</span>` : ''}
        </div>
        <div class="medicine-card__details">
            <div class="medicine-card__detail">
                <span class="medicine-card__detail-label">💊 Used For</span>
                <span class="medicine-card__detail-value">${escapeHtml(med.uses)}</span>
            </div>
            <div class="medicine-card__detail">
                <span class="medicine-card__detail-label">⏰ Dosage</span>
                <span class="medicine-card__detail-value medicine-card__detail-value--highlight">${escapeHtml(med.dosage_readable)}</span>
            </div>
            <div class="medicine-card__detail">
                <span class="medicine-card__detail-label">🍽️ Food Instruction</span>
                <span class="medicine-card__detail-value">${escapeHtml(med.food_instruction)}</span>
            </div>
            <div class="medicine-card__detail">
                <span class="medicine-card__detail-label">📅 Duration</span>
                <span class="medicine-card__detail-value">${escapeHtml(med.duration)}</span>
            </div>
            ${priceHtml}
            ${med.side_effects ? `
            <div class="medicine-card__detail medicine-card__detail--full">
                <span class="medicine-card__detail-label">⚡ Possible Side Effects</span>
                <span class="medicine-card__detail-value">${escapeHtml(med.side_effects)}</span>
            </div>` : ''}
            ${availabilityHtml}
            ${manufacturerHtml}
            ${warningHtml}
        </div>
    </div>`;
}

function renderSchedule(schedule) {
    if (!schedule || Object.keys(schedule).length === 0) {
        scheduleGrid.innerHTML = '<p style="text-align:center;color:var(--text-muted);grid-column:1/-1;">No schedule data available</p>';
        return;
    }

    const slotIcons = {
        'Morning': '🌅',
        'Afternoon': '☀️',
        'Evening': '🌆',
        'Night': '🌙',
        'Night (before sleep)': '😴',
        'As needed': '🔔',
        'As directed by doctor': '👨‍⚕️',
        'Immediately': '⚡',
        'Alternate days': '📆',
        'Weekly': '📅',
        'Twice a week': '📅',
    };

    const slotOrder = ['Morning', 'Afternoon', 'Evening', 'Night', 'Night (before sleep)', 'As needed', 'As directed by doctor'];

    // Sort schedule slots by the defined order
    const sortedKeys = Object.keys(schedule).sort((a, b) => {
        const idxA = slotOrder.indexOf(a);
        const idxB = slotOrder.indexOf(b);
        return (idxA === -1 ? 999 : idxA) - (idxB === -1 ? 999 : idxB);
    });

    let html = '';
    sortedKeys.forEach(slot => {
        const medicines = schedule[slot];
        const icon = slotIcons[slot] || '💊';

        let medsHtml = '';
        medicines.forEach(med => {
            medsHtml += `
            <div class="schedule__medicine">
                <span class="schedule__medicine-dot"></span>
                <span class="schedule__medicine-name">${escapeHtml(med.name)}</span>
                <span class="schedule__medicine-instruction">${escapeHtml(med.food_instruction || '')}</span>
            </div>`;
        });

        html += `
        <div class="schedule__slot">
            <div class="schedule__slot-header">
                <span class="schedule__slot-icon">${icon}</span>
                <span class="schedule__slot-title">${escapeHtml(slot)}</span>
                <span class="schedule__slot-count">${medicines.length}</span>
            </div>
            ${medsHtml}
        </div>`;
    });

    scheduleGrid.innerHTML = html;
}

// ===== Utilities =====

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showError(message) {
    errorText.textContent = message || 'Something went wrong';
    errorDetail.textContent = 'Please try again with a clearer prescription image';
    error.classList.add('show');
}
