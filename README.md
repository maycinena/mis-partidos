# Mis Partidos

Calendario combinado (`partidos.ics`) con los partidos de:

Athletic Club · Real Madrid · Boston Celtics · Boston Red Sox · New England Patriots · Selección de Guatemala · Municipal

- **Fuente:** API pública de ESPN, todas las competiciones de cada equipo (liga, copas, Champions, Concacaf, playoffs…).
- **Actualización:** GitHub Actions lo regenera cada 6 horas (`.github/workflows/actualizar.yml`).
- **Contenido:** próximos partidos y los de las últimas ~6 semanas con marcador. Partidos sin hora confirmada aparecen como evento de todo el día hasta que se confirme.

## Suscribirse en Apple Calendar

- **iPhone:** Ajustes → Apps → Calendario → Cuentas → Añadir cuenta → Otra → Añadir calendario suscrito, y pega la URL.
- **Mac:** Calendario → Archivo → Nuevo calendario suscrito, pega la URL. En "Ubicación" elige **iCloud** para que aparezca también en el iPhone, y en "Actualizar automáticamente" elige "Cada hora".

URL: `https://raw.githubusercontent.com/maycinena/mis-partidos/main/partidos.ics`

## Agregar o quitar equipos

Edita `equipos.json`. Cada equipo necesita su ID de ESPN (el número en la URL de su página en espn.com, p. ej. `espn.com/soccer/team/_/id/86` → `86`) y la lista de competiciones (códigos de liga de ESPN). Al guardar el cambio el calendario se regenera solo.

## Correr a mano

```
python3 partidos.py            # escribe partidos.ics
```
