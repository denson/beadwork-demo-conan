-- conan.db — hypergraph schema for the Conan O'Brien Superfan demo.
--
-- Design philosophy: store the GRAPH (entities + relationships + canonical
-- URLs); do not duplicate IMDb's content. When the agent talks about a
-- person, an episode, or a show, it opens the canonical_url in the user's
-- browser. The DB holds the structure; IMDb holds the data.
--
-- This file is regenerated from scripts/build_hypergraph.py and the
-- IMDb extraction JSONs on PRINCIPAL's machine. The .db itself is the
-- canonical shipped artifact; this .sql is the human-readable schema for
-- reviewability in PRs.

-- ---------------------------------------------------------------------------
-- nodes: people, episodes, shows, works (films/TV that Conan-guests were in)
-- ---------------------------------------------------------------------------
CREATE TABLE nodes (
  id            TEXT PRIMARY KEY,        -- nconst (people) or tconst (shows/episodes/works)
  kind          TEXT NOT NULL,           -- 'person' | 'show' | 'episode' | 'work'
  name          TEXT NOT NULL,           -- primary display name
  canonical_url TEXT,                    -- imdb.com URL the agent opens in the user's browser
  data_json     TEXT                     -- compact JSON of optional fields (year, runtime, rating, profession, etc.)
);
CREATE INDEX idx_nodes_kind ON nodes(kind);
CREATE INDEX idx_nodes_name ON nodes(name COLLATE NOCASE);

-- ---------------------------------------------------------------------------
-- edges: hyperedges connecting N nodes by role
--   'appearance': an episode + the people who appeared on it, each with a role
--   (future kinds: 'cast' for a film/show + its cast, 'broadcast' for a show + episode + date, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE edges (
  id        TEXT PRIMARY KEY,            -- e.g. 'appear-tt0626968'
  kind      TEXT NOT NULL,               -- 'appearance' | (future: 'cast' | 'broadcast' | ...)
  date      TEXT,                        -- ISO 'YYYY' or 'YYYY-MM-DD'; nullable
  data_json TEXT                         -- compact JSON of edge-level facts
);
CREATE INDEX idx_edges_kind_date ON edges(kind, date);

-- ---------------------------------------------------------------------------
-- participants: the node-in-edge relation, with role per participant
--   This is the join table that reifies hyperedges in a relational store.
--   Three nodes participating in one appearance event = three rows here,
--   all sharing the same edge_id but with different (node_id, role) pairs.
-- ---------------------------------------------------------------------------
CREATE TABLE participants (
  edge_id TEXT NOT NULL REFERENCES edges(id),
  node_id TEXT NOT NULL REFERENCES nodes(id),
  role    TEXT NOT NULL,                 -- 'venue' | 'host' | 'cohost' | 'announcer' | 'guest' |
                                         -- 'musical_guest' | 'bandleader' | 'band' |
                                         -- 'writer' | 'director' | 'producer' | 'editor' |
                                         -- 'actor' | 'actress' | 'cinematographer' | 'casting_director' |
                                         -- 'production_designer' | 'self' (fallback)
  PRIMARY KEY (edge_id, node_id, role)
);
CREATE INDEX idx_participants_node ON participants(node_id);
CREATE INDEX idx_participants_role ON participants(role);

-- ---------------------------------------------------------------------------
-- name_aliases: fuzzy-search index from any name string back to a node id
--   Seeded with the primary names. Extend at build time as we add Wikidata
--   birth-names, stage-names, etc.
-- ---------------------------------------------------------------------------
CREATE TABLE name_aliases (
  alias   TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES nodes(id),
  PRIMARY KEY (alias, node_id)
);
CREATE INDEX idx_aliases ON name_aliases(alias COLLATE NOCASE);

-- ---------------------------------------------------------------------------
-- Example queries (for the agent / for documentation):
-- ---------------------------------------------------------------------------

-- "Who is Tom Hanks?" — look up node by alias
--   SELECT n.* FROM nodes n
--     JOIN name_aliases a ON a.node_id = n.id
--     WHERE a.alias LIKE '%Tom Hanks%' AND n.kind = 'person';

-- "Show me Tom Hanks's IMDb page" — get canonical_url
--   SELECT canonical_url FROM nodes WHERE id = 'nm0000158';

-- "Which Conan episodes did Tom Hanks appear on as a guest?"
--   SELECT e.id, n.name, n.canonical_url, e.date
--     FROM edges e
--     JOIN participants p_guest ON p_guest.edge_id = e.id
--     JOIN participants p_ep    ON p_ep.edge_id = e.id AND p_ep.role = 'venue'
--     JOIN nodes n ON n.id = p_ep.node_id
--     WHERE p_guest.node_id = 'nm0000158'
--       AND p_guest.role IN ('guest', 'self')
--     ORDER BY e.date;

-- "Top guests by appearance count"
--   SELECT n.name, n.canonical_url, COUNT(*) AS appearances
--     FROM participants p
--     JOIN nodes n ON n.id = p.node_id
--     WHERE p.role = 'guest'
--     GROUP BY p.node_id
--     ORDER BY appearances DESC
--     LIMIT 50;
