-- Indices previstos en docs/modelo-de-datos.md, seccion 6

CREATE INDEX idx_atleta_nombre_norm ON atleta (nombre_normalizado);
CREATE INDEX idx_atleta_nombre_trgm ON atleta USING gin (nombre_normalizado gin_trgm_ops);

CREATE INDEX idx_pa_atleta ON participacion_atleta (atleta_id);

CREATE INDEX idx_part_noc ON participacion (noc_codigo);
CREATE INDEX idx_part_medalla ON participacion (medalla_id) WHERE medalla_id IS NOT NULL;
CREATE INDEX idx_part_evento_edicion ON participacion (evento_edicion_id);

CREATE INDEX idx_ee_edicion ON evento_edicion (edicion_id);

CREATE INDEX idx_sede_ciudad ON sede (ciudad_id);

CREATE INDEX idx_af_fuente_id ON atleta_fuente (fuente_id, id_en_fuente);
