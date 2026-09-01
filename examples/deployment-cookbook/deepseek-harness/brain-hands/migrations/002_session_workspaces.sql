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
