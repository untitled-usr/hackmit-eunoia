-- Allow friend requests to enter an explicit `expired` state.
-- SQLite cannot alter CHECK constraints in-place, so rebuild the table.
CREATE TABLE friend_request_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    requester_uid INTEGER NOT NULL,
    receiver_uid INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected', 'canceled', 'expired')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    FOREIGN KEY (requester_uid) REFERENCES user (uid) ON DELETE CASCADE,
    FOREIGN KEY (receiver_uid) REFERENCES user (uid) ON DELETE CASCADE
);

INSERT INTO friend_request_new (id, requester_uid, receiver_uid, message, status, created_at, updated_at, responded_at)
SELECT id, requester_uid, receiver_uid, message, status, created_at, updated_at, responded_at
FROM friend_request;

DROP TABLE friend_request;
ALTER TABLE friend_request_new RENAME TO friend_request;

CREATE INDEX friend_request_receiver_status ON friend_request (receiver_uid, status);
CREATE INDEX friend_request_requester_status ON friend_request (requester_uid, status);
CREATE UNIQUE INDEX friend_request_pending_unique
    ON friend_request (requester_uid, receiver_uid)
    WHERE status = 'pending';
