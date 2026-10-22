# Reporte de correcciones de datos (Fase 1 → Fase 3)

Generado por `scripts/01_corregir_datos.py` el 2026-10-21 19:51:04.

| Tabla | Fase 1 | Corregida |
|---|---|---|
| participacion | 212,376 | 221,204 |
| participacion_atleta | 314,679 | 314,679 |
| evento (flag es_por_equipos cambiado) | — | 119 eventos |
| noc (marcados como históricos) | — | 13 |
| noc (nombre de comité corregido) | — | 28 |

## C1 · Participaciones individuales fundidas
- Participaciones individuales con más de un atleta separadas: **6,400**.
- Participaciones nuevas creadas: **8,828** (ids desde 212377).
- Cada participación nueva guarda `participacion_origen_id` con el id de Fase 1.
- Ejemplos (participacion_id, NOC, evento_edicion_id, atletas fundidos): ('1', 'FRA', '1', 2); ('21', 'FRA', '18', 2); ('26', 'FRA', '20', 2); ('28', 'FRA', '22', 10); ('41', 'FRA', '3', 2)

## C2 · Eventos con es_por_equipos corregido
Total: 119 (de 1761). Pasaron a **individual**: 95; pasaron a **equipo**: 24.

Los 25 con más participaciones:

| Evento | Sexo | Antes | Ahora | Participaciones |
|---|---|---|---|---|
| Road Race, Individual | M | equipo | individual | 2,418 |
| Marathon | M | equipo | individual | 2,120 |
| Horizontal Bar | M | equipo | individual | 2,106 |
| Rings | M | equipo | individual | 2,096 |
| 100 metres Freestyle | M | equipo | individual | 1,332 |
| Foil, Individual | M | equipo | individual | 1,205 |
| Sabre, Individual | M | equipo | individual | 1,152 |
| 100 metres | F | equipo | individual | 1,067 |
| 100 metres Freestyle | F | equipo | individual | 989 |
| 10,000 metres | M | equipo | individual | 929 |
| High Jump | M | equipo | individual | 921 |
| Discus Throw | M | equipo | individual | 911 |
| 100 metres Backstroke | M | equipo | individual | 904 |
| 110 metres Hurdles | M | equipo | individual | 899 |
| 200 metres Breaststroke | M | equipo | individual | 895 |
| Foil, Individual | F | equipo | individual | 785 |
| Downhill | F | equipo | individual | 782 |
| 1,500 metres Freestyle | M | equipo | individual | 781 |
| 3,000 metres Steeplechase | M | equipo | individual | 779 |
| Pole Vault | M | equipo | individual | 731 |
| 100 metres Backstroke | F | equipo | individual | 727 |
| Hammer Throw | M | equipo | individual | 720 |
| Singles | M | equipo | individual | 712 |
| Welterweight | M | equipo | individual | 683 |
| 200 metres Breaststroke | F | equipo | individual | 673 |

## C4 · NOC
- Marcados como históricos: AHO, ANZ, BOH, CRT, FRG, NBO, NFL, RHO, SCG, UAR, WIF, YAR, YMD.
- Nombres corregidos: AHO (Curacao → Netherlands Antilles), AIN (AIN → Individual Neutral Athletes), ANZ (Australia → Australasia), BOH (Czech Republic → Bohemia), BOL (Boliva → Bolivia), CRT (Greece → Crete), EOR (EOR → Refugee Olympic Team), EUN (Russia → Unified Team), FRG (Germany → West Germany), GBR (UK → Great Britain), GDR (Germany → East Germany), IOA (IOA → Individual Olympic Athletes), NBO (Malaysia → North Borneo), NFL (Canada → Newfoundland), RHO (Zimbabwe → Rhodesia), ROC (Russia → Russian Olympic Committee), ROT (ROT → Refugee Olympic Team), SAA (Germany → Saar), SCG (Serbia → Serbia and Montenegro), TCH (Czech Republic → Czechoslovakia), TUV (TUV → Tuvalu), UAR (Syria → United Arab Republic), URS (Russia → Soviet Union), USA (USA → United States), WIF (Trinidad → West Indies Federation), YAR (Yemen → North Yemen), YMD (Yemen → South Yemen), YUG (Serbia → Yugoslavia)

## C5 · País
- Correcciones: [('Boliva', 'Bolivia')].
- Nombre en español agregado a 64 países.
