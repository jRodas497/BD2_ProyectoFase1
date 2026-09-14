-- Esquema de la Base de Datos Unificada de Olimpiadas — Proyecto Fase 1, inciso (c)
-- Fuente de verdad del modelo: docs/modelo-de-datos.md (15 entidades, 16 relaciones)

-- 3.1 Geografia y comites nacionales -----------------------------------------------------------

CREATE TABLE pais (
    pais_id      SERIAL PRIMARY KEY,
    nombre       VARCHAR(100) NOT NULL UNIQUE,
    codigo_iso3  CHAR(3)
);

CREATE TABLE noc (
    noc_codigo     CHAR(3) PRIMARY KEY,
    pais_id        INT REFERENCES pais(pais_id),
    nombre_comite  VARCHAR(120) NOT NULL,
    es_historico   BOOLEAN NOT NULL DEFAULT FALSE,
    notas          VARCHAR(200)
);

CREATE TABLE ciudad (
    ciudad_id  SERIAL PRIMARY KEY,
    pais_id    INT NOT NULL REFERENCES pais(pais_id),
    nombre     VARCHAR(100) NOT NULL,
    UNIQUE (pais_id, nombre)
);

-- 3.2 Ediciones y sedes -------------------------------------------------------------------------

CREATE TABLE edicion (
    edicion_id        SERIAL PRIMARY KEY,
    anio              SMALLINT NOT NULL CHECK (anio BETWEEN 1896 AND 2100),
    temporada         VARCHAR(8) NOT NULL CHECK (temporada IN ('Verano', 'Invierno')),
    numero_olimpiada  SMALLINT,
    nombre            VARCHAR(60) NOT NULL,
    fecha_inicio      DATE,
    fecha_fin         DATE,
    fue_cancelada     BOOLEAN NOT NULL DEFAULT FALSE,
    es_intercalada    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (anio, temporada)
);

CREATE TABLE sede (
    edicion_id    INT NOT NULL REFERENCES edicion(edicion_id),
    ciudad_id     INT NOT NULL REFERENCES ciudad(ciudad_id),
    es_principal  BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (edicion_id, ciudad_id)
);

-- 3.3 Catalogo deportivo ------------------------------------------------------------------------

CREATE TABLE deporte (
    deporte_id  SERIAL PRIMARY KEY,
    nombre      VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE disciplina (
    disciplina_id  SERIAL PRIMARY KEY,
    deporte_id     INT NOT NULL REFERENCES deporte(deporte_id),
    nombre         VARCHAR(80) NOT NULL,
    UNIQUE (deporte_id, nombre)
);

CREATE TABLE evento (
    evento_id       SERIAL PRIMARY KEY,
    disciplina_id   INT NOT NULL REFERENCES disciplina(disciplina_id),
    nombre          VARCHAR(200) NOT NULL,
    categoria_sexo  VARCHAR(10) CHECK (categoria_sexo IN ('M', 'F', 'Mixto', 'Abierto')),
    es_por_equipos  BOOLEAN NOT NULL,
    UNIQUE (disciplina_id, nombre, categoria_sexo)
);

CREATE TABLE evento_edicion (
    evento_edicion_id  SERIAL PRIMARY KEY,
    evento_id          INT NOT NULL REFERENCES evento(evento_id),
    edicion_id         INT NOT NULL REFERENCES edicion(edicion_id),
    UNIQUE (evento_id, edicion_id)
);

-- 3.4 Nucleo: atletas, participaciones y resultados ---------------------------------------------

CREATE TABLE medalla (
    medalla_id  SMALLINT PRIMARY KEY,
    nombre      VARCHAR(10) NOT NULL,
    orden       SMALLINT NOT NULL
);

CREATE TABLE atleta (
    atleta_id            SERIAL PRIMARY KEY,
    nombre_completo      VARCHAR(200) NOT NULL,
    nombre_usado         VARCHAR(150),
    nombre_normalizado   VARCHAR(150) NOT NULL,
    sexo                 CHAR(1) CHECK (sexo IN ('M', 'F', 'U')),
    fecha_nacimiento     DATE,
    fecha_defuncion      DATE,
    ciudad_nacimiento    VARCHAR(120),
    region_nacimiento    VARCHAR(120),
    pais_nacimiento_id   INT REFERENCES pais(pais_id),
    estatura_cm          SMALLINT CHECK (estatura_cm BETWEEN 100 AND 250),
    peso_kg              NUMERIC(5, 2) CHECK (peso_kg BETWEEN 25 AND 250)
);

CREATE TABLE participacion (
    participacion_id    BIGSERIAL PRIMARY KEY,
    evento_edicion_id   INT NOT NULL REFERENCES evento_edicion(evento_edicion_id),
    noc_codigo           CHAR(3) NOT NULL REFERENCES noc(noc_codigo),
    medalla_id           SMALLINT REFERENCES medalla(medalla_id),
    nombre_equipo        VARCHAR(150),
    es_por_equipos       BOOLEAN NOT NULL,
    puesto               SMALLINT,
    puesto_texto         VARCHAR(20),
    empatado             BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE participacion_atleta (
    participacion_id        BIGINT NOT NULL REFERENCES participacion(participacion_id),
    atleta_id               INT NOT NULL REFERENCES atleta(atleta_id),
    nombre_usado_en_evento  VARCHAR(200),
    PRIMARY KEY (participacion_id, atleta_id)
);

-- 3.5 Trazabilidad -------------------------------------------------------------------------------

CREATE TABLE fuente (
    fuente_id         SMALLSERIAL PRIMARY KEY,
    nombre            VARCHAR(100) NOT NULL,
    url               VARCHAR(300),
    fecha_extraccion  DATE,
    descripcion       VARCHAR(300)
);

CREATE TABLE atleta_fuente (
    atleta_id          INT NOT NULL REFERENCES atleta(atleta_id),
    fuente_id          SMALLINT NOT NULL REFERENCES fuente(fuente_id),
    id_en_fuente       VARCHAR(40) NOT NULL,
    nombre_en_fuente   VARCHAR(200),
    metodo_match       VARCHAR(30) CHECK (metodo_match IN ('espina', 'exacto', 'nombre+noc+anio', 'nuevo')),
    confianza          NUMERIC(3, 2) CHECK (confianza BETWEEN 0 AND 1),
    PRIMARY KEY (atleta_id, fuente_id, id_en_fuente)
);
