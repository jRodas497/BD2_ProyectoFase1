-- Catalogos estaticos que no vienen de ningun CSV fuente

INSERT INTO medalla (medalla_id, nombre, orden) VALUES
    (1, 'Oro', 1),
    (2, 'Plata', 2),
    (3, 'Bronce', 3);

INSERT INTO fuente (nombre, url, descripcion) VALUES
    ('Olympedia (KeithGalli/Olympics-Dataset)', 'https://github.com/KeithGalli/Olympics-Dataset', 'F1 — espina dorsal de atleta, puesto y biografia'),
    ('Kaggle 120 years of Olympic history', 'https://www.kaggle.com/datasets/heesoo37/120-years-of-olympic-history-athletes-and-results', 'F2 — ciudad sede, equipos, catalogo NOC-region'),
    ('Kaggle Summer Olympics Medals 1896-2024', 'https://www.kaggle.com/datasets/stefanydeoliveira/summer-olympics-medals-1896-2024', 'F3 — Tokio 2020 y Paris 2024'),
    ('DataCamp DataLab r-olympics', 'https://www.datacamp.com/datalab/datasets/r-olympics', 'F4 — subconjunto de muestra de F2');
