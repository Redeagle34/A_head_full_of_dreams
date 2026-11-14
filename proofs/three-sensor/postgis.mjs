import assert from 'node:assert/strict';
import { createReadStream } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { PGlite } from './.data/node_modules/@electric-sql/pglite/dist/index.js';
import { postgis } from './.data/node_modules/@electric-sql/pglite-postgis/dist/index.js';

const file = (name) => new URL('./.data/outputs/' + name, import.meta.url);
const databaseDir = process.argv[2];
const options = { extensions: { postgis } };
let db = await PGlite.create(databaseDir ?? 'memory://', options);
const insert = `
    INSERT INTO observations
    SELECT id, sensor, platform, state, product, batch, confidence, time_utc,
           ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
           ST_SetSRID(ST_GeomFromGeoJSON(footprint), 4326)
    FROM jsonb_to_recordset($1::jsonb)
        AS r(id text, sensor text, platform text, state text, product text, batch text,
             confidence text, time_utc timestamptz, lon float8, lat float8, footprint jsonb)
    ON CONFLICT (id) DO NOTHING
`;

async function load(tx) {
    const input = createInterface({ input: createReadStream(file('national.ndjson')) });
    let batch = [];
    for await (const line of input) {
        batch.push(line);
        if (batch.length === 1000) {
            await tx.query(insert, ['[' + batch.join(',') + ']']);
            batch = [];
        }
    }
    if (batch.length) await tx.query(insert, ['[' + batch.join(',') + ']']);
}

try {
    await db.exec('CREATE EXTENSION IF NOT EXISTS postgis');
    await db.exec(`
        CREATE TABLE IF NOT EXISTS observations (
            id text PRIMARY KEY,
            sensor text NOT NULL, platform text NOT NULL, state text NOT NULL,
            product text NOT NULL, batch text NOT NULL, confidence text NOT NULL,
            observed_at timestamptz NOT NULL,
            centroid geography(Point, 4326) NOT NULL,
            footprint geometry(Polygon, 4326) NOT NULL
        );
        CREATE INDEX IF NOT EXISTS observations_centroid_idx ON observations USING gist (centroid);
        CREATE INDEX IF NOT EXISTS observations_footprint_idx ON observations USING gist (footprint);
        CREATE INDEX IF NOT EXISTS observations_time_idx ON observations (observed_at);
    `);
    const proof = JSON.parse(await readFile(file('summary.json'), 'utf8'));
    await db.transaction(load);
    await db.transaction(load);
    if (databaseDir) {
        await db.close();
        db = await PGlite.create(databaseDir, options);
    }
    const version = (await db.query('SELECT postgis_version() AS postgis')).rows[0].postgis;
    const count = (await db.query('SELECT count(*)::int AS count FROM observations')).rows[0].count;
    assert.equal(count, proof.distinct_us_native_observations);
    const { longitude, latitude, radius_km } = proof.selection;
    const { rows: nearby } = await db.query(`
        SELECT id, sensor, ST_AsGeoJSON(footprint)::json AS geometry
        FROM observations
        WHERE ST_DWithin(centroid, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
          AND observed_at >= $4 AND observed_at < $5
        ORDER BY id
    `, [longitude, latitude, radius_km * 1000, ...proof.observed_interval_utc]);
    const geojson = JSON.parse(await readFile(file('nearby.geojson'), 'utf8'));
    assert.deepEqual(nearby.map(row => row.id), geojson.features.map(feature => feature.id).sort());
    const { rows: regional } = await db.query(`
        WITH sample AS (
            SELECT DISTINCT ON (state) state, id, centroid, observed_at
            FROM observations WHERE state IN ('GA', 'CA') ORDER BY state, id
        )
        SELECT state, EXISTS (
            SELECT 1 FROM observations o
            WHERE o.id = sample.id AND ST_DWithin(o.centroid, sample.centroid, 20000)
              AND o.observed_at >= sample.observed_at
              AND o.observed_at < sample.observed_at + interval '1 second'
        ) AS found FROM sample ORDER BY state
    `)
    assert.deepEqual(regional, [{ state: 'CA', found: true }, { state: 'GA', found: true }]);
    const result = { reopened_persistent_database: Boolean(databaseDir), regional, postgis: version, distinct_observations_after_replay: count,
                     nearby_selected: nearby.length, matches_export_ids: true };
    await writeFile(file('postgis-summary.json'), JSON.stringify(result, null, 2));
    console.log(result);
} finally {
    await db.close();
}

