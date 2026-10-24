CREATE TABLE items (id int PRIMARY KEY, name text NOT NULL, value int NOT NULL);
INSERT INTO items SELECT g, 'item-' || g, g * 7 FROM generate_series(1, 1000) g;
