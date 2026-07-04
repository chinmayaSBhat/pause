from pyngrok import ngrok
import time

print("Starting ngrok tunnel on port 8000...")
try:
    public_url = ngrok.connect(8000).public_url
    print(f"\n==========================================")
    print(f"SUCCESS! Your app is live on ngrok:")
    print(f"Ngrok Tunnel URL: {public_url}")
    print(f"==========================================\n")
    print("Keeping tunnel alive... Press CTRL+C to stop.")
    
    while True:
        time.sleep(1)
except Exception as e:
    print(f"Error starting ngrok: {e}")
    print("You may need to authenticate ngrok first.")
except KeyboardInterrupt:
    print("Closing ngrok tunnel.")
    ngrok.kill()
