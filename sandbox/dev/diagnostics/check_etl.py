import requests

def main():
    try:
        r = requests.get("http://localhost:8081/api/etl/status")
        print("ETL:", r.status_code, r.text)
    except Exception as e:
        print("ETL: FAILED", e)

if __name__ == "__main__":
    main()
