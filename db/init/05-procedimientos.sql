-- Stored procedures del inciso (d) y (e) — ver docs/modelo-de-datos.md, seccion 7.
-- Ambos despliegan su salida con RAISE NOTICE (no SELECT), para poder correrse con
-- CALL sp_...(...) desde psql o dBeaver y ver el resultado como texto en la consola.

-- ================================================================================================
-- (d) sp_info_atleta(p_nombre, p_deporte, p_pais, p_anio)
-- ================================================================================================
-- Busqueda por nombre parcial (ILIKE, sin distincion de mayusculas) sobre nombre_completo,
-- nombre_usado y nombre_normalizado — puede matchear a mas de un atleta (nombres repetidos),
-- en cuyo caso despliega cada uno por separado.
-- Filtros opcionales (NULL = sin filtrar): deporte (nombre), pais (nombre del NOC o su codigo
-- de 3 letras), anio de la edicion.

CREATE OR REPLACE PROCEDURE sp_info_atleta(
    p_nombre   VARCHAR,
    p_deporte  VARCHAR DEFAULT NULL,
    p_pais     VARCHAR DEFAULT NULL,
    p_anio     INT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    r_atleta      RECORD;
    r_res         RECORD;
    v_encontrado  BOOLEAN := FALSE;
    v_oro         BIGINT;
    v_plata       BIGINT;
    v_bronce      BIGINT;
    v_total       BIGINT;
BEGIN
    FOR r_atleta IN
        SELECT a.*
        FROM atleta a
        WHERE a.nombre_completo    ILIKE '%' || p_nombre || '%'
           OR a.nombre_usado       ILIKE '%' || p_nombre || '%'
           OR a.nombre_normalizado ILIKE '%' || p_nombre || '%'
        ORDER BY a.nombre_completo
    LOOP
        v_encontrado := TRUE;

        RAISE NOTICE '================================================================';
        RAISE NOTICE 'ATLETA: % (id %)', r_atleta.nombre_completo, r_atleta.atleta_id;
        IF r_atleta.nombre_usado IS NOT NULL AND r_atleta.nombre_usado <> r_atleta.nombre_completo THEN
            RAISE NOTICE '  Tambien conocido como: %', r_atleta.nombre_usado;
        END IF;
        RAISE NOTICE '  Sexo: %  |  Nacimiento: %  |  Fallecimiento: %',
            COALESCE(r_atleta.sexo, '?'),
            COALESCE(r_atleta.fecha_nacimiento::TEXT, 'desconocida'),
            COALESCE(r_atleta.fecha_defuncion::TEXT, '—');
        RAISE NOTICE '  Lugar de nacimiento: %, %',
            COALESCE(r_atleta.ciudad_nacimiento, '?'), COALESCE(r_atleta.region_nacimiento, '?');
        RAISE NOTICE '  Estatura: % cm  |  Peso: % kg',
            COALESCE(r_atleta.estatura_cm::TEXT, '?'), COALESCE(r_atleta.peso_kg::TEXT, '?');

        -- Medallero del atleta, con los mismos filtros de deporte/pais/anio
        SELECT
            COUNT(*) FILTER (WHERE med.orden = 1),
            COUNT(*) FILTER (WHERE med.orden = 2),
            COUNT(*) FILTER (WHERE med.orden = 3),
            COUNT(*)
        INTO v_oro, v_plata, v_bronce, v_total
        FROM participacion_atleta pa
        JOIN participacion p        ON p.participacion_id = pa.participacion_id
        JOIN evento_edicion ee      ON ee.evento_edicion_id = p.evento_edicion_id
        JOIN edicion ed             ON ed.edicion_id = ee.edicion_id
        JOIN evento ev              ON ev.evento_id = ee.evento_id
        JOIN disciplina disc        ON disc.disciplina_id = ev.disciplina_id
        JOIN deporte dep            ON dep.deporte_id = disc.deporte_id
        JOIN noc n                  ON n.noc_codigo = p.noc_codigo
        LEFT JOIN medalla med       ON med.medalla_id = p.medalla_id
        WHERE pa.atleta_id = r_atleta.atleta_id
          AND (p_deporte IS NULL OR dep.nombre ILIKE '%' || p_deporte || '%')
          AND (p_pais    IS NULL OR n.nombre_comite ILIKE '%' || p_pais || '%'
                                 OR n.noc_codigo = UPPER(p_pais))
          AND (p_anio    IS NULL OR ed.anio = p_anio);

        RAISE NOTICE '  Participaciones (con filtros aplicados): %  |  Medallas: Oro % / Plata % / Bronce %',
            v_total, v_oro, v_plata, v_bronce;
        RAISE NOTICE '  ----------------------------------------------------------------';

        FOR r_res IN
            SELECT
                ed.anio, ed.temporada, dep.nombre AS deporte, disc.nombre AS disciplina,
                ev.nombre AS evento, n.nombre_comite, n.noc_codigo,
                p.nombre_equipo, p.es_por_equipos,
                p.puesto_texto, p.empatado, med.nombre AS medalla,
                pa.nombre_usado_en_evento
            FROM participacion_atleta pa
            JOIN participacion p        ON p.participacion_id = pa.participacion_id
            JOIN evento_edicion ee      ON ee.evento_edicion_id = p.evento_edicion_id
            JOIN edicion ed             ON ed.edicion_id = ee.edicion_id
            JOIN evento ev              ON ev.evento_id = ee.evento_id
            JOIN disciplina disc        ON disc.disciplina_id = ev.disciplina_id
            JOIN deporte dep            ON dep.deporte_id = disc.deporte_id
            JOIN noc n                  ON n.noc_codigo = p.noc_codigo
            LEFT JOIN medalla med       ON med.medalla_id = p.medalla_id
            WHERE pa.atleta_id = r_atleta.atleta_id
              AND (p_deporte IS NULL OR dep.nombre ILIKE '%' || p_deporte || '%')
              AND (p_pais    IS NULL OR n.nombre_comite ILIKE '%' || p_pais || '%'
                                     OR n.noc_codigo = UPPER(p_pais))
              AND (p_anio    IS NULL OR ed.anio = p_anio)
            ORDER BY ed.anio, dep.nombre, ev.nombre
        LOOP
            RAISE NOTICE '  % % | % / % — % | NOC: % (%)% | Puesto: % | Medalla: %',
                r_res.anio, r_res.temporada, r_res.deporte, r_res.disciplina, r_res.evento,
                r_res.nombre_comite, r_res.noc_codigo,
                CASE WHEN r_res.es_por_equipos THEN ' [equipo: ' || COALESCE(r_res.nombre_equipo, '?') || ']' ELSE '' END,
                COALESCE(NULLIF(r_res.puesto_texto, ''), '—') || CASE WHEN r_res.empatado THEN ' (empate)' ELSE '' END,
                COALESCE(r_res.medalla, '—');
        END LOOP;

        IF v_total = 0 THEN
            RAISE NOTICE '  (sin participaciones que cumplan los filtros dados)';
        END IF;
    END LOOP;

    IF NOT v_encontrado THEN
        RAISE NOTICE 'No se encontro ningun atleta cuyo nombre coincida con "%"', p_nombre;
    END IF;
END;
$$;

-- ================================================================================================
-- (e) sp_info_pais(p_pais, p_anio, p_temporada, p_deporte)
-- ================================================================================================
-- p_pais matchea por nombre de pais (tabla PAIS) o por nombre/codigo de comite olimpico (NOC),
-- para cubrir tanto paises actuales como NOC historicos disueltos (URSS, RFA, etc. — D-004b).
-- Filtros opcionales: anio de la edicion, temporada ('Verano'/'Invierno'), deporte (nombre).

CREATE OR REPLACE PROCEDURE sp_info_pais(
    p_pais       VARCHAR,
    p_anio       INT DEFAULT NULL,
    p_temporada  VARCHAR DEFAULT NULL,
    p_deporte    VARCHAR DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    r_noc         RECORD;
    r_sede        RECORD;
    r_anio        RECORD;
    r_medalla     RECORD;
    v_encontrado  BOOLEAN := FALSE;
    v_oro         BIGINT;
    v_plata       BIGINT;
    v_bronce      BIGINT;
    v_total       BIGINT;
BEGIN
    FOR r_noc IN
        SELECT DISTINCT n.noc_codigo, n.nombre_comite, n.es_historico, n.pais_id, pa.nombre AS pais_nombre
        FROM noc n
        LEFT JOIN pais pa ON pa.pais_id = n.pais_id
        WHERE n.nombre_comite ILIKE '%' || p_pais || '%'
           OR n.noc_codigo = UPPER(p_pais)
           OR pa.nombre ILIKE '%' || p_pais || '%'
        ORDER BY n.nombre_comite
    LOOP
        v_encontrado := TRUE;

        RAISE NOTICE '================================================================';
        RAISE NOTICE 'COMITE OLIMPICO (NOC): % (%)%',
            r_noc.nombre_comite, r_noc.noc_codigo,
            CASE WHEN r_noc.es_historico THEN '  [historico / disuelto]' ELSE '' END;
        RAISE NOTICE '  Pais asociado: %', COALESCE(r_noc.pais_nombre, '(sin pais asociado en el modelo)');

        -- Sedes: años y ciudades en las que el pais de este NOC fue anfitrion
        RAISE NOTICE '  --- Sede olimpica ---';
        IF r_noc.pais_id IS NULL THEN
            RAISE NOTICE '  No aplica: este NOC no tiene un pais asociado en el modelo.';
        ELSE
            FOR r_sede IN
                SELECT ed.anio, ed.temporada, c.nombre AS ciudad, s.es_principal
                FROM sede s
                JOIN ciudad c   ON c.ciudad_id = s.ciudad_id
                JOIN edicion ed ON ed.edicion_id = s.edicion_id
                WHERE c.pais_id = r_noc.pais_id
                  AND (p_anio      IS NULL OR ed.anio = p_anio)
                  AND (p_temporada IS NULL OR ed.temporada = p_temporada)
                ORDER BY ed.anio
            LOOP
                RAISE NOTICE '  Sede en % (%) — %',
                    r_sede.anio, r_sede.temporada,
                    r_sede.ciudad || CASE WHEN r_sede.es_principal THEN '' ELSE ' [sede secundaria]' END;
            END LOOP;
            IF NOT FOUND THEN
                RAISE NOTICE '  Nunca ha sido sede (con los filtros dados).';
            END IF;
        END IF;

        -- Medallero (cuenta entradas/participaciones, no atletas — D-004b / seccion 7)
        SELECT
            COUNT(*) FILTER (WHERE med.orden = 1),
            COUNT(*) FILTER (WHERE med.orden = 2),
            COUNT(*) FILTER (WHERE med.orden = 3),
            COUNT(*)
        INTO v_oro, v_plata, v_bronce, v_total
        FROM participacion p
        JOIN evento_edicion ee ON ee.evento_edicion_id = p.evento_edicion_id
        JOIN edicion ed        ON ed.edicion_id = ee.edicion_id
        JOIN evento ev         ON ev.evento_id = ee.evento_id
        JOIN disciplina disc   ON disc.disciplina_id = ev.disciplina_id
        JOIN deporte dep       ON dep.deporte_id = disc.deporte_id
        LEFT JOIN medalla med  ON med.medalla_id = p.medalla_id
        WHERE p.noc_codigo = r_noc.noc_codigo
          AND (p_anio      IS NULL OR ed.anio = p_anio)
          AND (p_temporada IS NULL OR ed.temporada = p_temporada)
          AND (p_deporte   IS NULL OR dep.nombre ILIKE '%' || p_deporte || '%');

        RAISE NOTICE '  --- Resumen (con filtros aplicados) ---';
        RAISE NOTICE '  Participaciones (entradas): %  |  Medallas: Oro % / Plata % / Bronce %',
            v_total, v_oro, v_plata, v_bronce;

        -- Años de participacion
        RAISE NOTICE '  --- Anios de participacion ---';
        FOR r_anio IN
            SELECT DISTINCT ed.anio, ed.temporada
            FROM participacion p
            JOIN evento_edicion ee ON ee.evento_edicion_id = p.evento_edicion_id
            JOIN edicion ed        ON ed.edicion_id = ee.edicion_id
            JOIN evento ev         ON ev.evento_id = ee.evento_id
            JOIN disciplina disc   ON disc.disciplina_id = ev.disciplina_id
            JOIN deporte dep       ON dep.deporte_id = disc.deporte_id
            WHERE p.noc_codigo = r_noc.noc_codigo
              AND (p_anio      IS NULL OR ed.anio = p_anio)
              AND (p_temporada IS NULL OR ed.temporada = p_temporada)
              AND (p_deporte   IS NULL OR dep.nombre ILIKE '%' || p_deporte || '%')
            ORDER BY ed.anio
        LOOP
            RAISE NOTICE '  %  (%)', r_anio.anio, r_anio.temporada;
        END LOOP;
        IF v_total = 0 THEN
            RAISE NOTICE '  (sin participaciones que cumplan los filtros dados)';
        END IF;

        -- Detalle de resultados con medalla
        RAISE NOTICE '  --- Resultados con medalla ---';
        FOR r_medalla IN
            SELECT ed.anio, ed.temporada, dep.nombre AS deporte, ev.nombre AS evento,
                   p.nombre_equipo, p.es_por_equipos, p.puesto_texto, med.nombre AS medalla
            FROM participacion p
            JOIN evento_edicion ee ON ee.evento_edicion_id = p.evento_edicion_id
            JOIN edicion ed        ON ed.edicion_id = ee.edicion_id
            JOIN evento ev         ON ev.evento_id = ee.evento_id
            JOIN disciplina disc   ON disc.disciplina_id = ev.disciplina_id
            JOIN deporte dep       ON dep.deporte_id = disc.deporte_id
            JOIN medalla med       ON med.medalla_id = p.medalla_id
            WHERE p.noc_codigo = r_noc.noc_codigo
              AND (p_anio      IS NULL OR ed.anio = p_anio)
              AND (p_temporada IS NULL OR ed.temporada = p_temporada)
              AND (p_deporte   IS NULL OR dep.nombre ILIKE '%' || p_deporte || '%')
            ORDER BY ed.anio, med.orden
        LOOP
            RAISE NOTICE '  % % | % — % -> % (%)',
                r_medalla.anio, r_medalla.temporada, r_medalla.deporte,
                r_medalla.evento || CASE WHEN r_medalla.es_por_equipos THEN ' [equipo: ' || COALESCE(r_medalla.nombre_equipo, '?') || ']' ELSE '' END,
                r_medalla.medalla, COALESCE(NULLIF(r_medalla.puesto_texto, ''), '—');
        END LOOP;
        IF NOT FOUND THEN
            RAISE NOTICE '  (sin medallas que cumplan los filtros dados)';
        END IF;
    END LOOP;

    IF NOT v_encontrado THEN
        RAISE NOTICE 'No se encontro ningun pais/NOC que coincida con "%"', p_pais;
    END IF;
END;
$$;
