# StockPro — Sistema de Gestión de Inventario

Sistema web completo para gestión de mercancía, construido con Flask (Python).

## Funcionalidades

- ✅ **Inventario en tiempo real** — Stock actualizado automáticamente con cada movimiento
- ✅ **Login con roles** — Admin, Editor y Viewer con diferentes permisos
- ✅ **Ingreso de mercancía** — Entradas, salidas y ajustes de stock
- ✅ **Historial de movimientos** — Registro completo de quién hizo qué y cuándo
- ✅ **Alertas de stock bajo** — Notificaciones visuales cuando un producto llega al mínimo
- ✅ **Categorías de productos** — Organizá tu catálogo con colores personalizados
- ✅ **Presupuestos para clientes** — Generá presupuestos con ítems, descuentos e IVA
- ✅ **Exportar PDF** — Presupuesto profesional listo para enviar al cliente

## Estructura del proyecto

```
stockpro/
├── app.py              # Aplicación principal Flask
├── wsgi.py             # Punto de entrada para producción
├── requirements.txt    # Dependencias Python
├── render.yaml         # Configuración para Render.com
└── templates/          # Páginas HTML
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── products.html
    ├── product_form.html
    ├── categories.html
    ├── movements.html
    ├── budgets.html
    ├── budget_form.html
    ├── budget_view.html
    └── users.html
```

## Credenciales iniciales

- **Usuario:** `admin`
- **Contraseña:** `admin123`

> ⚠️ Cambiá la contraseña del admin apenas inicies el sistema.

---

## Cómo subir a Render.com (GRATIS)

### Paso 1 — Crear repositorio en GitHub

1. Ir a [github.com](https://github.com) y crear cuenta (si no tenés)
2. Crear nuevo repositorio: `New repository` → Nombre: `stockpro` → `Create repository`
3. Subir todos los archivos de esta carpeta al repositorio

### Paso 2 — Crear cuenta en Render.com

1. Ir a [render.com](https://render.com) → `Get Started for Free`
2. Registrarse con la cuenta de GitHub

### Paso 3 — Desplegar el proyecto

1. En Render, hacer clic en `New +` → `Web Service`
2. Conectar el repositorio de GitHub `stockpro`
3. Configurar:
   - **Name:** stockpro
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn wsgi:app`
4. En `Environment Variables`, agregar:
   - `SECRET_KEY` = (cualquier texto largo y aleatorio, ej: `mi-clave-super-secreta-2024`)
5. Clic en `Create Web Service`
6. ¡Listo! En 3-5 minutos tu app estará en `https://stockpro.onrender.com`

### Paso 4 — Acceder al sistema

- Ingresar a la URL que provee Render
- Login con `admin` / `admin123`
- Crear usuarios adicionales desde el menú `Usuarios`

---

## Prueba local (opcional)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
python app.py

# Abrir en el navegador
http://localhost:5000
```

---

## Roles de usuario

| Rol    | Ver inventario | Modificar stock | Crear presupuestos | Gestionar usuarios |
|--------|:--------------:|:---------------:|:------------------:|:-----------------:|
| Admin  | ✅             | ✅              | ✅                 | ✅                |
| Editor | ✅             | ✅              | ✅                 | ❌                |
| Viewer | ✅             | ❌              | ❌                 | ❌                |
