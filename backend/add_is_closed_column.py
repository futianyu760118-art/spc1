import psycopg2

conn = psycopg2.connect('postgresql://root:123456@192.168.0.127:5432/spc_db')
cur = conn.cursor()
cur.execute("ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS is_closed BOOLEAN NOT NULL DEFAULT false")
conn.commit()
print('Column is_closed added to sale_order successfully')

# Also update alembic_version to mark our migration as applied
cur.execute("SELECT version_num FROM alembic_version")
current = [row[0] for row in cur.fetchall()]
print(f'Current alembic versions: {current}')

# Stamp to our new revision
cur.execute("DELETE FROM alembic_version")
cur.execute("INSERT INTO alembic_version (version_num) VALUES ('add_is_closed_to_sale_order')")
conn.commit()
print('Alembic version stamped to add_is_closed_to_sale_order')
conn.close()
