# API FX Prod - Available Scripts

<div dir="rtl">

## 🚀 التشغيل السريع

### **تشغيل كل الخوادم (Backend + Frontend)**
```bash
# باستخدام Batch
run.bat

# أو باستخدام PowerShell (أفضل)
.\run.ps1
```

### **تشغيل Backend فقط**
```bash
run-backend.bat
```

### **تشغيل Frontend فقط**
```bash
run-frontend.bat
```

### **إعادة تشغيل البوابة بعد تحديث الكود**
```bash
# باستخدام Batch
restart.bat

# أو باستخدام PowerShell
.\restart.ps1
```

يبحث عن العملية المستمعة على المنفذ 8790، ويتأكد أن سطر أوامرها يحتوي `gateway.py`
قبل إيقافها، ثم يبدأ النسخة الجديدة وينتظر `/health` حتى يظهر رقم الإصدار الجديد.

### **إيقاف كل الخوادم**
```bash
# باستخدام Batch
stop.bat

# أو باستخدام PowerShell (أفضل)
.\stop.ps1
```

---

## 📦 الإعداد الأولي

### **تثبيت كل شيء تلقائياً**
```bash
setup.bat
```

هذا سيقوم بـ:
- ✓ إنشاء المجلدات اللازمة
- ✓ تثبيت تبعيات Python
- ✓ تثبيت تبعيات Node.js
- ✓ التحقق من المتطلبات

---

## 🐳 النشر (Docker)

### **بناء وتشغيل الحاويات**
```bash
deploy.bat
```

### **أوامر Docker مفيدة**
```bash
# عرض السجلات
docker-compose logs -f

# إيقاف الحاويات
docker-compose down

# إعادة التشغيل
docker-compose restart

# إعادة البناء
docker-compose up --build -d
```

---

## 📝 الملفات المتاحة

| الملف | الوصف |
|------|------|
| `run.bat` | تشغيل Backend + Frontend |
| `run.ps1` | نفس الأمر لكن PowerShell (أفضل) |
| `run-backend.bat` | تشغيل Backend فقط |
| `run-frontend.bat` | تشغيل Frontend فقط |
| `restart.bat` | إعادة تشغيل البوابة وتحميل آخر إصدار |
| `restart.ps1` | نفس الأمر لكن PowerShell |
| `stop.bat` | إيقاف كل الخوادم |
| `stop.ps1` | نفس الأمر لكن PowerShell |
| `setup.bat` | الإعداد الأولي |
| `deploy.bat` | نشر باستخدام Docker |

---

## 🔧 الاستخدام اليدوي

### **Backend**
```bash
# تثبيت التبعيات
pip install -r requirements.txt

# تشغيل الخادم
python gateway.py

# أو باستخدام uvicorn مباشرة
uvicorn gateway:app --host 0.0.0.0 --port 8790 --reload
```

### **Frontend**
```bash
cd modern-workspace

# تثبيت التبعيات
npm install

# تشغيل خادم التطوير
npm run dev

# بناء للإنتاج
npm run build
```

---

## 🌐 الروابط

بعد التشغيل:
- **Frontend**: http://localhost:5173
- **Backend**: http://127.0.0.1:8790
- **API Docs**: http://127.0.0.1:8790/docs
- **Status**: http://127.0.0.1:8790/status

---

## ⚡ اختصارات مفيدة

### **إنشاء اختصار على سطح المكتب**
1. انقر بزر الماوس الأيمن على `run.bat`
2. اختر "Send to" → "Desktop (create shortcut)"
3. أعد تسمية الاختصار إلى "API FX Prod"
4. انقر نقراً مزدوجاً للتشغيل السريع!

---

## 🐛 حل المشاكل

### **المشكلة: "Python is not installed"**
- تأكد من تثبيت Python 3.11+
- أضف Python إلى PATH
- تحقق: `python --version`

### **المشكلة: "Node.js is not installed"**
- تأكد من تثبيت Node.js
- أضف Node.js إلى PATH
- تحقق: `node --version`

### **المشكلة: "Port 8790 already in use"**
- أوقف البرنامج الذي يستخدم المنفذ
- أو غير المنفذ في `.env`:
  ```
  GATEWAY_PORT=8788
  ```

### **المشكلة: "Module not found"**
```bash
# أعد تثبيت التبعيات
pip install -r requirements.txt --force-reinstall
```

---

## 📞 المساعدة

للمزيد من المعلومات:
- راجع [`README.md`](../README.md)
- راجع `DEVELOPMENT_PLAN.md` و`FIXES.md` في هذا المجلد
- اقرأ [`CONTRIBUTING.md`](../CONTRIBUTING.md) قبل فتح issue أو PR

</div>
