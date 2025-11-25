import psycopg2

def main():
    try:
        conn = psycopg2.connect(
            dbname="fiberstack",
            user="fs_user",
            password="fs_pass",
            host="localhost",
            port=5433
        )
        cur = conn.cursor()
        cur.execute("SELECT NOW();")
        ts = cur.fetchone()
        print("Timescale OK:", ts)
    except Exception as e:
        print("Timescale: FAILED", e)

if __name__ == "__main__":
    main()
