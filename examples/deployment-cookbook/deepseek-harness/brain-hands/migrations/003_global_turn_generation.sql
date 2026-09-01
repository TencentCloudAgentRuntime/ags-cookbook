CREATE TABLE IF NOT EXISTS dsh_turn_generation (
  singleton TINYINT UNSIGNED NOT NULL,
  generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (singleton),
  CONSTRAINT chk_dsh_turn_generation_singleton CHECK (singleton = 1)
) ENGINE=InnoDB;

INSERT IGNORE INTO dsh_turn_generation (singleton, generation) VALUES (1, 0);
