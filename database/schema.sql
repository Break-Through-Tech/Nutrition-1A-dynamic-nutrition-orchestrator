-- Enable pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

--USDA Foods Table
CREATE TABLE IF NOT EXISTS foods (
    fdc_id BIGINT PRIMARY KEY,
    data_type TEXT,
    description TEXT NOT NULL,
    food_category_id TEXT,
    publication_date DATE,

    -- Nutritional information
    calories_kcal DOUBLE PRECISION,
    protein_g DOUBLE PRECISION,
    fat_g DOUBLE PRECISION,
    carbs_g DOUBLE PRECISION,
    fiber_g DOUBLE PRECISION,
    sugars_g DOUBLE PRECISION,
    sodium_mg DOUBLE PRECISION,
    potassium_mg DOUBLE PRECISION,
    calcium_mg DOUBLE PRECISION,
    iron_mg DOUBLE PRECISION
);