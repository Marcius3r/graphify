# Chapita: activar Stripe paso a paso

Ya está hecho en la web y en el servidor:

- **Botón «Pagar ahora»** en la reserva. Abre la página de pago oficial de **Stripe Checkout**, donde se paga con Visa, Mastercard, Apple Pay, Google Pay y Bizum (si Stripe te lo activa).
- **La web nunca ve ni guarda datos de tarjeta:** el cliente los escribe en la página de Stripe.
- **Un pedido solo pasa a «pagado» cuando Stripe lo confirma** con un aviso firmado (webhook). Si la firma no es válida, se rechaza. Si el importe no cuadra, te avisa de una incidencia en lugar de marcarlo como pagado.
- **Al confirmarse el pago**, el cliente recibe la confirmación automática (por WhatsApp o por correo, según lo que eligió) y a ti te llega «💳 Pago recibido CH-…» a garciatellomarc@gmail.com.
- **En Chapita Admin → Inicio → Ventas** ves lo cobrado en total y este mes, los pagos completados, los pedidos pendientes y el historial con el importe y el método de pago (Bizum o tarjeta).

**El botón «Pagar ahora» está oculto hasta que Stripe esté conectado de verdad.** No hay nada simulado.

---

## Lo que cuesta (plan estándar, sin cuotas)

Datos de la página de precios de Stripe para España. Compruébalos en **stripe.com/es/pricing** antes de activar, porque pueden cambiar:

| Tipo de pago | Comisión por cobro |
|---|---|
| Tarjeta europea normal (la mayoría de clientes) | **1,5 % + 0,25 €** |
| Tarjeta premium o de empresa europea | 2,8 % + 0,25 € (aprox.) |
| Tarjeta del Reino Unido | 2,5 % + 0,25 € |
| Tarjeta de fuera de Europa | 3,25 % + 0,25 € (aprox.) + 2 % si hay cambio de moneda |

- **Sin cuota mensual ni coste de alta.** Solo pagas cuando cobras.
- **Ejemplo:** una chapa de 6,90 € con tarjeta europea → comisión de 0,35 € → recibes **6,55 €**.
- **Si devuelves un pago**, Stripe no te devuelve la comisión.
- **Apple Pay y Google Pay** cuestan lo mismo que la tarjeta.
- **Bizum por Stripe:** mira su precio en tu panel (Configuración → Métodos de pago) antes de activarlo.

No actives nada más: «Billing», «Radar for Fraud Teams», «Tax», etc. son extras de pago que no necesitas.

---

## Paso 1 · Crear la cuenta

1. Entra en **https://stripe.com/es** → **Empezar ahora**.
2. Pon tu correo (garciatellomarc@gmail.com), tu nombre, el país **España** y una contraseña.
3. Confirma el correo que te envía Stripe.

## Paso 2 · Activar los pagos (datos del negocio)

En el panel de Stripe → **Activar pagos** (o **Configuración → Datos de la empresa**). Te pedirá:

- **Tipo de negocio:** «Particular / autónomo» o «Empresa», según tu caso. Si tienes dudas legales o fiscales, consúltalo con tu gestor; yo no relleno datos legales por ti.
- **Datos personales:** nombre, fecha de nacimiento, dirección y DNI/NIE.
- **Web del negocio:** `https://chapita-opal.vercel.app`
- **Descripción:** por ejemplo «Venta de chapas identificativas NFC para perros impresas en 3D».
- **Descriptor en el extracto:** `CHAPITA` (es lo que verá el cliente en su banco).

## Paso 3 · Verificar tu identidad

Stripe te pedirá una foto de tu **DNI/NIE** por las dos caras y, a veces, un selfie. Se hace desde el propio panel o desde el móvil con el código QR que te muestra.

## Paso 4 · Tu cuenta bancaria (IBAN)

**Configuración → Pagos y transferencias (Payouts) → Añadir cuenta bancaria** → escribe tu **IBAN** (ES…). Ahí te llegará el dinero.

Stripe hace transferencias automáticas. En España suele ser a diario, con unos días de margen en los primeros pagos; lo ves en esa misma pantalla.

## Paso 5 · Métodos de pago

**Configuración → Métodos de pago** y activa:

- **Tarjetas** (Visa y Mastercard vienen activadas).
- **Apple Pay** y **Google Pay**: en Stripe Checkout funcionan sin hacer nada más.
- **Bizum**: si aparece en la lista, actívalo. Si no aparece, es que Stripe aún no lo ofrece en tu cuenta. Mientras tanto, la opción de Bizum manual de la web (al 627 157 395) sigue funcionando.

La web muestra automáticamente los métodos que tengas activados aquí. No hay que tocar nada más.

## Paso 6 · Dame la clave y lo conecto

1. **Desarrolladores → Claves de API.**
2. Para probar sin dinero real, activa arriba **«Modo de prueba»** y copia la **Clave secreta** (`sk_test_…`). Para cobrar de verdad, desactívalo y copia la de producción (`sk_live_…`).
3. Pásamela. Yo:
   - La guardo en la tabla privada del servidor (la web nunca la ve).
   - **Registro el webhook automáticamente** en tu Stripe (no tienes que hacerlo tú).
   - Hago un pago de prueba de principio a fin y compruebo que el pedido pasa a «pagado» solo cuando Stripe lo confirma.
   - Activo el botón «Pagar ahora» en la web.

Recomiendo empezar con la clave de **prueba** (`sk_test_`). Con ella puedes pagar con la tarjeta de pruebas `4242 4242 4242 4242` (cualquier fecha futura y CVC) sin mover dinero. Cuando veas que todo va bien, me das la `sk_live_` y queda funcionando con pagos reales.
