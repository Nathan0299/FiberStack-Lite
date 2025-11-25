import requests

def main():
    try:
        r = requests.get("http://localhost:8081/api/status")
        print("API:", r.status_code, r.text)
    except Exception as e:
        print("API: FAILED", e)

if __name__ == "__main__":
    main()
