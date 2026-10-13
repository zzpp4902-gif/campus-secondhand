// 图片压缩并转 base64
function compressImage(file, maxWidth = 800, quality = 0.7) {
    return new Promise((resolve, reject) => {
        if (!file) {
            resolve('');
            return;
        }
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = new Image();
            img.onload = function() {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                if (width > maxWidth) {
                    height = (height * maxWidth) / width;
                    width = maxWidth;
                }
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                const base64 = canvas.toDataURL('image/jpeg', quality);
                resolve(base64);
            };
            img.onerror = reject;
            img.src = e.target.result;
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// 发布/编辑商品表单：图片上传预览 + 压缩
function setupImageUpload(inputId, previewId, hiddenId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const hidden = document.getElementById(hiddenId);
    if (!input) return;

    input.addEventListener('change', async function() {
        const file = this.files[0];
        if (!file) return;
        if (!file.type.startsWith('image/')) {
            alert('请选择图片文件');
            return;
        }
        try {
            const base64 = await compressImage(file);
            hidden.value = base64;
            preview.src = base64;
            preview.classList.add('show');
        } catch (e) {
            alert('图片处理失败：' + e.message);
        }
    });
}

// 发布表单提交前校验
function setupPublishForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', function(e) {
        const title = document.getElementById('title').value.trim();
        const price = document.getElementById('price').value.trim();
        const image = document.getElementById('image_base64').value.trim();
        if (!title) {
            e.preventDefault();
            alert('请填写商品标题');
            return;
        }
        if (!price || isNaN(price) || parseInt(price) < 0) {
            e.preventDefault();
            alert('请填写有效的价格（非负整数）');
            return;
        }
        if (!image) {
            e.preventDefault();
            alert('请上传商品图片');
            return;
        }
    });
}

// 注册表单校验
function setupRegisterForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;
    form.addEventListener('submit', function(e) {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const nickname = document.getElementById('nickname').value.trim();
        if (username.length < 3 || username.length > 20) {
            e.preventDefault();
            alert('用户名需 3-20 个字符');
            return;
        }
        if (password.length < 6) {
            e.preventDefault();
            alert('密码至少 6 位');
            return;
        }
        if (!nickname) {
            e.preventDefault();
            alert('请填写昵称');
            return;
        }
    });
}

// 意向申请弹窗
function setupApplyModal() {
    const openBtn = document.getElementById('openApplyModal');
    const modal = document.getElementById('applyModal');
    const closeBtn = document.getElementById('closeModal');
    if (!openBtn || !modal) return;

    openBtn.addEventListener('click', function() {
        modal.classList.add('show');
    });
    closeBtn.addEventListener('click', function() {
        modal.classList.remove('show');
    });
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    });
}

// 导航下拉菜单开关
function toggleDropdown(id) {
    const dropdown = document.getElementById(id).closest('.nav-dropdown');
    const wasOpen = dropdown.classList.contains('open');
    // 先关闭所有下拉
    document.querySelectorAll('.nav-dropdown.open').forEach(d => d.classList.remove('open'));
    // 再切换当前
    if (!wasOpen) {
        dropdown.classList.add('open');
    }
}

// 点击外部关闭所有下拉
function setupDropdownClose() {
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.nav-dropdown')) {
            document.querySelectorAll('.nav-dropdown.open').forEach(d => d.classList.remove('open'));
        }
    });
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    setupImageUpload('image_input', 'image_preview', 'image_base64');
    setupPublishForm('publishForm');
    setupRegisterForm();
    setupApplyModal();
    setupDropdownClose();
});
