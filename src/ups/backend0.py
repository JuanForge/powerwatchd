import subprocess
import traceback


class session:
    def __init__(self, ups_name: str, host: str = "127.0.0.1", port: int = 2162):
        self.name = ups_name
        self.host = host
        self.port = port
    
    def status(self):
        try:
            result = subprocess.run(
                ['upsc', f'{self.name}@{self.host}:{self.port}'],
                capture_output=True, text=True, timeout=5, check=False
            )
            if result.returncode != 0:
                print("Erreur: Impossible d'interroger l'UPS.")
                print(result.stderr.strip())
                return None
            
            info = {}
            for line in result.stdout.splitlines():
                if ':' in line:
                    key, val = line.split(':', 1)
                    info[key.strip()] = val.strip()
            
            return info
        except Exception as e:
            print(f"Exception lors de la vérification UPS : {e}")
            print(traceback.format_exc())
            return None

if __name__ == "__main__":
    session2 = session("ecoEaton", "localhost")