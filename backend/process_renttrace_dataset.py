import json

from app.services.renttrace_dataset import process_dataset


if __name__ == "__main__":
    print(json.dumps(process_dataset(), ensure_ascii=False, indent=2))
