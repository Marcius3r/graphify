# Chapita · web pública y Chapita Admin

Sitio estático publicado en Vercel (carpeta raíz del proyecto de Vercel: `chapita-web`).

- `/` — tienda pública: personalizador 3D, reservas (llama a la función `crear-pedido` de Supabase y abre WhatsApp).
- `/admin/` — Chapita Admin (PWA privada). El acceso real lo controlan Supabase Auth, las políticas RLS y la función `admin-api`.
- `img/` — mapas de zonas para recolorear la foto real de la chapa.

El servidor (base de datos y funciones) está en el proyecto de Supabase `chapita-tienda`.
