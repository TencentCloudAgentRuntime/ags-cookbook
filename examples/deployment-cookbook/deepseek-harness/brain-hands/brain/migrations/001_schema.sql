CREATE TABLE IF NOT EXISTS dsh_store_state (
  singleton TINYINT UNSIGNED NOT NULL,
  store_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (singleton),
  CONSTRAINT chk_dsh_store_state_singleton CHECK (singleton = 1)
) ENGINE=InnoDB;

INSERT IGNORE INTO dsh_store_state (singleton, store_id) VALUES (1, UUID());

CREATE TABLE IF NOT EXISTS dsh_sessions (
  session_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  header_json JSON NOT NULL,
  incarnation CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  next_seq BIGINT UNSIGNED NOT NULL DEFAULT 0,
  revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (session_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dsh_session_events (
  session_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  seq BIGINT UNSIGNED NOT NULL,
  event_json JSON NOT NULL,
  PRIMARY KEY (session_id, seq),
  CONSTRAINT fk_dsh_session_events_session
    FOREIGN KEY (session_id) REFERENCES dsh_sessions (session_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS workspace_bindings (
  binding_mode ENUM('USER', 'SESSION') NOT NULL,
  binding_identity VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  state ENUM('PENDING', 'ACTIVE', 'FAILED') NOT NULL,
  generation BIGINT UNSIGNED NOT NULL,
  deployment_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NULL,
  affinity_id VARCHAR(1024) CHARACTER SET ascii COLLATE ascii_bin NULL,
  failure_code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (binding_mode, binding_identity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS turn_claims (
  session_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  holder_instance_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  generation BIGINT UNSIGNED NOT NULL,
  state ENUM('ACTIVE', 'COMPLETED', 'INTERRUPTED') NOT NULL,
  expires_at TIMESTAMP(6) NOT NULL,
  heartbeat_at TIMESTAMP(6) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (session_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dsh_session_workspaces (
  session_id VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  binding_mode ENUM('USER', 'SESSION') NOT NULL,
  binding_identity VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (session_id),
  KEY idx_dsh_session_workspaces_binding (binding_mode, binding_identity),
  CONSTRAINT fk_dsh_session_workspaces_session
    FOREIGN KEY (session_id) REFERENCES dsh_sessions (session_id) ON DELETE CASCADE,
  CONSTRAINT fk_dsh_session_workspaces_binding
    FOREIGN KEY (binding_mode, binding_identity)
    REFERENCES workspace_bindings (binding_mode, binding_identity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dsh_turn_generation (
  singleton TINYINT UNSIGNED NOT NULL,
  generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (singleton),
  CONSTRAINT chk_dsh_turn_generation_singleton CHECK (singleton = 1)
) ENGINE=InnoDB;

INSERT IGNORE INTO dsh_turn_generation (singleton, generation) VALUES (1, 0);
