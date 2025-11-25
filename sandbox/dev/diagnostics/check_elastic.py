import requests

def main():
    try:
        r = requests.get("http://localhost:9201")
        print("Elastic:", r.status_code)
    except Exception as e:
        print("Elastic: FAILED", e)

if __name__ == "__main__":
    main()
