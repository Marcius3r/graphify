# Chapita: conectar WhatsApp y Gmail (paso a paso)

Cuando termines esta guía, todo funcionará solo:

1. Un cliente reserva en la web → recibe por WhatsApp (y por correo, si lo dejó) el resumen y cómo pagar por Bizum.
2. Tú recibes el aviso en **Chapita Admin** y una copia en el **Gmail de la tienda**.
3. Miras tu banco, abres el pedido en Chapita Admin y pulsas **Confirmar pago**.
4. **El bot le escribe solo al cliente:** «¡Buenas noticias! Hemos confirmado correctamente tu pago del pedido CH-…».
5. Lo mismo con **Aceptar**, **Rechazar** (con motivo), **En preparación**, **Enviado** («¡Tu pedido CH-… ya está en camino! 📦») y **Completado**.

También puedes hacerlo desde el asistente del panel escribiendo, por ejemplo, «confirma pago CH-1234». Siempre te pedirá que confirmes antes.

> **Nunca pegues contraseñas ni tokens en el chat.** Cuando los tengas, escríbeme «listo» y te abriré ventanas seguras de Supabase para meterlos. Yo nunca veo los valores.

---

## Parte 1 · Gmail (10 minutos, gratis)

### 1. Crea el Gmail de la tienda
Entra en **accounts.google.com/signup** y crea una cuenta, por ejemplo `chapita.tienda@gmail.com`.

### 2. Activa la verificación en dos pasos
Con esa cuenta, entra en **myaccount.google.com/security** → **Verificación en dos pasos** → **Activar** (te pedirá tu móvil).
Sin esto, Google no deja crear el paso siguiente.

### 3. Crea una «contraseña de aplicación»
Entra en **myaccount.google.com/apppasswords**:
- Nombre de la aplicación: `Chapita`
- Pulsa **Crear**. Te saldrá una clave de 16 letras (por ejemplo `abcd efgh ijkl mnop`).
- **Cópiala. No me la pegues en el chat.**

Es una clave solo para que Chapita envíe correos; no es tu contraseña de Gmail y la puedes borrar cuando quieras desde esa misma página.

### 4. Dímelo
Escríbeme **«Gmail listo»** y la **dirección** del Gmail (la dirección sí puedes escribirla). Te abriré dos ventanas seguras:

| Ventana | Qué pegas |
|---|---|
| `GMAIL_USER` | la dirección, p. ej. `chapita.tienda@gmail.com` |
| `GMAIL_APP_PASSWORD` | la clave de 16 letras |

Después hago una prueba de envío y te enseño en el panel (Ajustes → Gmail de la tienda) que pone **Conectado**.

---

## Parte 2 · WhatsApp (20 minutos, gratis para probar)

La app **WhatsApp Business** del móvil no deja que un programa responda solo. Para eso hace falta la **API de WhatsApp de Meta**, que es gratuita para empezar.

### 1. Crea la app en Meta
1. Entra en **developers.facebook.com** con tu Facebook. Si te lo pide, regístrate como desarrollador (gratis).
2. **Mis apps** → **Crear app** → elige la opción de **WhatsApp** («Conectar con clientes a través de WhatsApp»).
3. Nombre: **Chapita**. Si te pide una cuenta comercial (Meta Business), deja que la cree.

### 2. Saca los 3 datos (en el menú WhatsApp → Configuración de la API)
| Dato | Dónde | Ventana segura |
|---|---|---|
| **Token de acceso** | Botón **Generar token** | `WHATSAPP_TOKEN` |
| **Identificador del número de teléfono** | Debajo del número «De» | `WHATSAPP_PHONE_NUMBER_ID` |
| **Clave secreta de la app** | Menú **Configuración de la app → Básica → Clave secreta → Mostrar** | `WHATSAPP_APP_SECRET` |

En esa misma pantalla, en **«Para»**, añade tu móvil **+34 627 157 395** y pon el código que te llega. Con el número de prueba de Meta solo se puede escribir a los números que añadas aquí.

### 3. Conecta los mensajes que llegan (webhook)
Menú **WhatsApp → Configuración → Webhook → Editar**:
- **URL de devolución de llamada:** `https://zmosqfoiddndrlieuleb.supabase.co/functions/v1/whatsapp-webhook`
- **Token de verificación:** `a78cb50930efa05b4d6e4c9967aee159`

Pulsa **Verificar y guardar**. Luego, en la lista de campos, busca **messages** y pulsa **Suscribirse**.

### 4. Dímelo
Escríbeme **«WhatsApp listo»** y el **número de prueba** que te da Meta (ese sí puedes escribirlo). Te abro las 3 ventanas seguras, cambio la tienda para que use ese número y hacemos juntos una reserva de prueba:
1. Reservas desde la web con tu móvil.
2. Te llega la respuesta automática del bot.
3. Pulsas **Confirmar pago** en Chapita Admin.
4. Te llega «Pago confirmado» por WhatsApp (y por correo si lo pusiste).

### 5. Más adelante: tu número de verdad
- **Número:** en **Configuración de la API → Añadir número de teléfono**. Meta pide que ese número no esté en la app de WhatsApp. Si al añadir el 627 157 395 te ofrece usarlo a la vez en **WhatsApp Business** («coexistencia»), acéptalo; si no, usa un segundo número (una SIM o eSIM barata) solo para la tienda.
- **Token permanente** (el de prueba caduca en 24 h): **Meta Business → Configuración del negocio → Usuarios del sistema** → crea uno administrador → **Generar token** con los permisos `whatsapp_business_messaging` y `whatsapp_business_management`, sin caducidad.
- **Plantilla** para escribir a clientes que llevan más de 24 h sin hablarte: **WhatsApp → Plantillas** → nombre `chapita_actualizacion`, categoría **Utilidad**, idioma **Español**:
  > Hola {{1}}, hay novedades en tu pedido {{2}} de Chapita: {{3}}. Gracias por confiar en nosotros.

---

## Lo que cuesta
- **Gmail:** gratis (hasta unos 500 correos al día).
- **WhatsApp:** gratis para probar. Con tu número real, responder a un cliente que te ha escrito suele ser gratis; los mensajes que inicias tú pasadas 24 h tienen un pequeño coste por mensaje en Meta.
- **Web, panel y servidor:** en los planes gratuitos de Vercel y Supabase.
