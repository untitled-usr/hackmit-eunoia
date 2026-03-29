-- Friend requests (accept / reject / cancel flow)
CREATE TABLE friend_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    requester_uid INTEGER NOT NULL,
    receiver_uid INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected', 'canceled')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    FOREIGN KEY (requester_uid) REFERENCES user (uid) ON DELETE CASCADE,
    FOREIGN KEY (receiver_uid) REFERENCES user (uid) ON DELETE CASCADE
);

CREATE INDEX friend_request_receiver_status ON friend_request (receiver_uid, status);
CREATE INDEX friend_request_requester_status ON friend_request (requester_uid, status);

-- At most one pending request per pair (requester -> receiver)
CREATE UNIQUE INDEX friend_request_pending_unique
    ON friend_request (requester_uid, receiver_uid)
    WHERE status = 'pending';

-- Undirected friendship; soft-delete with deleted_by for asymmetric UX
CREATE TABLE friendship (
    uid_low INTEGER NOT NULL,
    uid_high INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    deleted_by INTEGER,
    PRIMARY KEY (uid_low, uid_high),
    CHECK (uid_low < uid_high),
    FOREIGN KEY (uid_low) REFERENCES user (uid) ON DELETE CASCADE,
    FOREIGN KEY (uid_high) REFERENCES user (uid) ON DELETE CASCADE,
    FOREIGN KEY (deleted_by) REFERENCES user (uid) ON DELETE SET NULL
);

CREATE INDEX friendship_active ON friendship (uid_low, uid_high) WHERE deleted_at IS NULL;

-- Directed block list (blocker blocks blocked)
CREATE TABLE user_block (
    blocker_uid INTEGER NOT NULL,
    blocked_uid INTEGER NOT NULL,
    reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (blocker_uid, blocked_uid),
    FOREIGN KEY (blocker_uid) REFERENCES user (uid) ON DELETE CASCADE,
    FOREIGN KEY (blocked_uid) REFERENCES user (uid) ON DELETE CASCADE
);

CREATE INDEX user_block_blocker ON user_block (blocker_uid);
CREATE INDEX user_block_blocked ON user_block (blocked_uid);

-- Read-friendly views for external services / analytics
CREATE VIEW friendship_edge_v AS
SELECT uid_low AS uid, uid_high AS peer_uid, created_at, updated_at, deleted_at, deleted_by
FROM friendship
UNION ALL
SELECT uid_high AS uid, uid_low AS peer_uid, created_at, updated_at, deleted_at, deleted_by
FROM friendship;

CREATE VIEW user_block_edge_v AS
SELECT blocker_uid AS uid, blocked_uid AS peer_uid, created_at, updated_at
FROM user_block;
