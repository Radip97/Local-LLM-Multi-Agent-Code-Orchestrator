import random
import time
from datetime import datetime, timedelta

def generate_mock_ip():
    return f"{random.randint(1, 223)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"

def generate_mock_log(filename="access.log", lines=250):
    methods = ["GET", "POST", "PUT", "DELETE"]
    endpoints = [
        "/index.html", "/about.html", "/contact.html", "/api/v1/users",
        "/api/v1/products", "/api/v1/orders?id=99", "/images/logo.png",
        "/css/styles.css", "/js/main.js", "/blog/post-1?author=radip",
        "/checkout", "/login", "/register", "/admin/settings"
    ]
    status_codes = [200, 200, 200, 200, 301, 302, 400, 401, 403, 404, 404, 500, 503]
    referrers = [
        "-", "http://www.google.com", "http://www.bing.com",
        "https://github.com/Radip97", "http://example.com/home"
    ]
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "curl/7.81.0"
    ]

    base_time = datetime.now() - timedelta(days=1)
    
    with open(filename, "w", encoding="utf-8") as f:
        for i in range(lines):
            # Generate timestamps in chronological order
            log_time = base_time + timedelta(seconds=i * random.randint(10, 60))
            time_str = log_time.strftime("%d/%b/%Y:%H:%M:%S +0000")
            
            ip = generate_mock_ip()
            method = random.choice(methods)
            endpoint = random.choice(endpoints)
            status = random.choice(status_codes)
            
            # 304, 403, 404, 500, etc. might have 0 bytes or '-'
            if status in [301, 302, 404, 500]:
                bytes_sent = "-" if random.random() < 0.3 else str(random.randint(0, 500))
            elif status == 200:
                bytes_sent = str(random.randint(500, 150000))
            else:
                bytes_sent = "0"
                
            referrer = random.choice(referrers)
            agent = random.choice(user_agents)
            
            # Format: IP - - [time] "METHOD endpoint HTTP/1.1" STATUS BYTES "REFERRER" "USER_AGENT"
            log_line = f'{ip} - - [{time_str}] "{method} {endpoint} HTTP/1.1" {status} {bytes_sent} "{referrer}" "{agent}"\n'
            f.write(log_line)
            
    print(f"Successfully generated {lines} mock log entries in '{filename}'.")

if __name__ == "__main__":
    generate_mock_log()
