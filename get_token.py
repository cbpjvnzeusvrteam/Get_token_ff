import json
import requests
import os
import time
import threading
from flask import Flask, jsonify

app = Flask(__name__)

# Biến cờ để kiểm soát việc chạy của luồng nền
running_task = None
# Initialize task_status with a default, clearly indicating initial state
task_status_data = {
    "status": "Chưa khởi động",
    "last_run_time": None,
    "next_run_estimate": "Chưa xác định"
}
# Use a lock for thread-safe access to task_status_data
task_status_lock = threading.Lock()

def upload_tokens_to_api(tokens_data):
    """
    Gửi dữ liệu token lên API PHP.
    """
    api_upload_url = "https://zproject.x10.mx/uptoken.php" # Sử dụng http nếu không có SSL

    if not tokens_data:
        print("Không có token nào để tải lên API.")
        return False # Trả về False nếu không có token để upload

    try:
        # Chuyển đổi dữ liệu token thành chuỗi JSON
        json_payload = json.dumps(tokens_data, ensure_ascii=False)

        # Gửi POST request với dữ liệu JSON
        response = requests.post(api_upload_url, data={'tokens': json_payload})
        response.raise_for_status()  # Ném lỗi nếu status code là lỗi (4xx hoặc 5xx)

        print(f"Phản hồi từ API upload: {response.text}")
        if "success" in response.text.lower():
            print("Đã tải token lên API thành công.")
            return True
        else:
            print("API trả về lỗi hoặc không thành công khi tải token.")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gửi dữ liệu lên API upload: {e}")
        return False
    except Exception as e:
        print(f"Lỗi không xác định khi upload token: {e}")
        return False

def get_tokens_and_upload():
    """
    Đọc tài khoản từ accounts.json, lấy token từ API
    và tải lên API PHP.
    """
    accounts_file = 'accounts.json'
    api_token_generator_url = "https://ff-token-generator.vercel.app/token"

    if not os.path.exists(accounts_file):
        print(f"Lỗi: Không tìm thấy file '{accounts_file}'. Vui lòng đảm bảo file này nằm cùng thư mục với script.")
        return []

    try:
        with open(accounts_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except json.JSONDecodeError:
        print(f"Lỗi: File '{accounts_file}' không phải là định dạng JSON hợp lệ.")
        return []
    except Exception as e:
        print(f"Lỗi khi đọc file '{accounts_file}': {e}")
        return []

    tokens_data = []
    print(f"Đang xử lý {len(accounts)} tài khoản...")
    for account in accounts:
        uid = account.get("uid")
        password = account.get("password")

        if not uid or not password:
            print(f"Bỏ qua tài khoản không hợp lệ: {account}")
            continue

        params = {
            "uid": uid,
            "password": password
        }

        try:
            response = requests.get(api_token_generator_url, params=params)
            response.raise_for_status()
            data = response.json()
            token = data.get("token")

            if token:
                tokens_data.append({
                    "uid": uid,
                    "token": token
                })
                print(f"Đã lấy token cho UID: {uid}")
            else:
                print(f"Không tìm thấy token trong phản hồi cho UID: {uid}")

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi gọi API cho UID {uid}: {e}")
        except json.JSONDecodeError:
            print(f"Lỗi: Phản hồi API cho UID {uid} không phải là JSON hợp lệ.")
        except Exception as e:
            print(f"Lỗi không xác định khi xử lý UID {uid}: {e}")

    return tokens_data

def background_token_refresher():
    global task_status_data
    while True:
        with task_status_lock:
            task_status_data["status"] = "Đang chạy quá trình lấy và tải token..."
            task_status_data["last_run_time"] = None # Reset last run time
        print("\n--- Bắt đầu quá trình lấy và tải token ---")
        tokens = get_tokens_and_upload()

        success = False
        if tokens:
            if upload_tokens_to_api(tokens):
                success = True
                message = "Cập nhật token thành công."
            else:
                message = "Cập nhật token thất bại."
        else:
            message = "Không có token nào được lấy thành công."

        current_time = time.time()
        next_run_time = current_time + 8 * 3600

        with task_status_lock:
            task_status_data["status"] = message
            task_status_data["last_run_time"] = current_time
            # SỬA LỖI Ở ĐÂY:
            task_status_data["next_run_estimate"] = time.strftime('%H:%M:%S', time.localtime(next_run_time))

        # SỬA LỖI Ở ĐÂY (dòng print):
        print(f"--- Kết thúc quá trình. Chờ 8 tiếng để lọc lại token (lần tiếp theo lúc {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_run_time))}) ---")
        time.sleep(8 * 3600) # Chờ 8 tiếng (8 * 3600 giây)

# Route chính để kiểm tra trạng thái
@app.route('/')
def home():
    with task_status_lock:
        current_status = task_status_data.copy()

    # Format the last_run_time if it exists
    last_run_display = "Chưa có"
    if current_status["last_run_time"]:
        # CHỖ NÀY LÀ NGUYÊN NHÂN GÂY LỖI:
        # last_run_display = time.strftime('%Y-%m-%d %H:%M:%S', current_status["last_run_time"])

        # CÁCH SỬA LỖI: Chuyển timestamp thành struct_time bằng time.localtime()
        last_run_display = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_status["last_run_time"]))


    return jsonify({
        "status": "Running",
        "message": "API Token Refresher đang hoạt động.",
        "last_task_status": current_status["status"],
        "last_run_at": last_run_display,
        "next_run_estimate": f"Lần chạy tiếp theo dự kiến khoảng {current_status['next_run_estimate']} sau lần chạy cuối cùng thành công."
    })

# Route để kích hoạt chạy thủ công (chỉ để kiểm tra hoặc debug)
@app.route('/run_now')
def run_now():
    # Using a separate thread to not block the request
    threading.Thread(target=get_tokens_and_upload_single_run).start()
    return jsonify({
        "status": "triggered",
        "message": "Đã yêu cầu chạy lại quá trình lọc token.",
        "note": "Kết quả sẽ được cập nhật trong logs và trạng thái sau khi hoàn thành."
    })

def get_tokens_and_upload_single_run():
    """Chức năng chạy một lần khi kích hoạt thủ công."""
    global task_status_data
    print("\n--- Bắt đầu chạy thủ công quá trình lấy và tải token ---")
    tokens = get_tokens_and_upload()

    success = False
    if tokens:
        if upload_tokens_to_api(tokens):
            success = True
            message = "Chạy thủ công thành công."
        else:
            message = "Chạy thủ công thất bại."
    else:
        message = "Chạy thủ công không có token nào được lấy thành công."

    current_time = time.time()
    next_run_time = current_time + 8 * 3600 # This will be misleading for a manual run but keeps the structure

    with task_status_lock:
        task_status_data["status"] = message
        task_status_data["last_run_time"] = current_time
        # SỬA LỖI Ở ĐÂY:
        task_status_data["next_run_estimate"] = time.strftime('%H:%M:%S', time.localtime(next_run_time))

    print("--- Kết thúc chạy thủ công ---")


if __name__ == "__main__":
    # Khởi động luồng nền để tự động lọc token
    running_task = threading.Thread(target=background_token_refresher)
    running_task.daemon = True # Cho phép luồng nền thoát khi luồng chính thoát
    running_task.start()

    # Chạy ứng dụng Flask trên cổng được Render cung cấp
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)
