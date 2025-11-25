import requests

def main():
    try:
        r = requests.get("http://localhost:8080")
        print("Dashboard:", r.status_code)
    except Exception as e:
        print("Dashboard: FAILED", e)

if __name__ == "__main__":
    main()
