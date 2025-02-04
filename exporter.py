import time, json, requests, os, asyncio, threading
import logging.config
from prometheus_client import start_http_server, Gauge
from http.server import BaseHTTPRequestHandler, HTTPServer

base_coin = os.environ.get("BASE_COIN")
mining_coin = os.environ.get("MINING_COIN")
currency = os.environ.get("CURRENCY")
addy = os.environ.get("MINING_ADDRESS")
name = os.environ.get("RIG_NAME")
hive_url = os.environ.get("HIVE_URL")
wallet_address = os.environ.get("WALLET_ADDY")
hive_farm_id = os.environ.get("FARM_ID")
hive_worker_id = os.environ.get("WORKER_ID")
electric = float(os.environ.get("ELECTRIC_COST"))
hive_key = os.environ.get("HIVE_KEY")
cc_key = os.environ.get("CC_KEY")
explorer_url = os.environ.get("EXPLORER_URL")
decimal = int(f'1{"0" * int(os.environ.get("MINING_DECIMALS", 8))}')
polling_interval_seconds = int(os.getenv("POLLING_INTERVAL_SECONDS", 300))
exporter_port = int(os.getenv("EXPORTER_PORT", 9877))
api_port = int(os.environ.get("APP_PORT", 80))
# init logger

class PromExporter:
    def __init__(self):
        
        """
        Prometheus Exporter Object
        executeProcess() - Main Process Loop
        fetchData() - Aggregates all Data
        getGauges() - Initializes the Prometheus Collectors
        setGauges() - Sets Metrics
        writeFile() - Writes response Data to json file for apache to serve
        """
        logger.info(f"Init PromExporter")
        self.hive_headers = {"Authorization": f"Bearer {hive_key}"}
        self.getGauges()
        self.endpoints = {
            "price": f"",
            "2miners": f"{mining_coin.lower()}.2miners.com/api/accounts/{addy}",
            "balance": f"{explorer_url}{wallet_address}",
            "hive": {
                'farm': f"{hive_url}/api/v2/farms/{hive_farm_id}/stats",
                'worker': f"{hive_url}/api/v2/farms/{hive_farm_id}/workers/{hive_worker_id}"
            }
        }
        self.data = {
            "price": {},
            "2miners": {},
            "balance": {},
            "hive": {
                'farm': {},
                'worker': {}
            }
        }

    def executeProcess(self):
        # Metrics Loop
        logger.info(f"Beginning Exporter Running Loop")
        while True:
            self.fetchData()
            self.setMetrics()
            self.writeFile()
            logger.info(f"Sleeping for  : {polling_interval_seconds}(s)")
            time.sleep(polling_interval_seconds)

    def fetchData(self):
        logger.info(f"Begin Data Extraction..")
        for key in self.endpoints.keys():

            if key == "price":
                logger.info(f"Hitting cryptoCompare for Price Data")

                self.data[key][f"{key}_{base_coin}"] = requests.get(
                    self.priceURL(base_coin, currency)).json()

                self.data[key][f"{key}_{mining_coin}"] = requests.get(
                    self.priceURL(mining_coin, currency)).json()

            elif key == "balance":
                logger.info(f"Hitting Explorer for Wallet Balance Data")

                self.data[key] = requests.get(f"https://{self.endpoints[key]}").json()

                self.data[key].update({f"wallet_{key}_{base_coin}": round(
                    self.data[key][wallet_address]["final_balance"] / decimal, 5, )})

                self.data[key].update({f"wallet_{key}_{currency}": round(
                    self.data[key][f"wallet_{key}_{base_coin}"]
                    * self.data["price"][f"price_{base_coin}"][currency], 2,)})

            elif key == "hive":
                logger.info(f"Hitting Hive for Farm Stats")

                self.data[key]['farm'] = requests.get(
                    f"https://{self.endpoints[key]['farm']}", headers=self.hive_headers).json()
                
                logger.info(f"Hitting Hive for Worker Stats")
                self.data[key]['worker'] = requests.get(
                    f"https://{self.endpoints[key]['worker']}", headers=self.hive_headers).json()

                self.data[key]['farm'][f"power_cost_{currency}"] = round(
                    self.powerConversion(self.data[key]['farm']["stats"]["power_draw"]), 2)

                self.data[key]['farm']["mining_profitability"] = round(
                    self.data["2miners"][f"unpaid_last_24_hr_{currency}"]
                    - self.data[key]['farm'][f"power_cost_{currency}"], 2,)

                self.data[key]['farm']["mining_profitability_percent"] = round(
                    (self.data[key]['farm']["mining_profitability"]
                     / self.data["2miners"][f"unpaid_last_24_hr_{currency}"]) * 100, 2,)
                

            elif key == "2miners":
                logger.info(f"Hitting 2Miners for Account Stats Data")

                self.data[key] = requests.get(f"https://{self.endpoints[key]}").json()

                self.data[key].update({f"unpaid_balance_{mining_coin}": round(
                    self.data[key]["stats"]["balance"] / decimal, 5)})

                self.data[key].update({f"unpaid_balance_{currency}": round(
                    self.data[key][f"unpaid_balance_{mining_coin}"] *
                    self.data["price"][f"price_{mining_coin}"][currency],2,)})

                self.data[key].update({f"unpaid_last_24_hr_{mining_coin}": round(
                    self.data[key]["sumrewards"][2]["reward"] / decimal, 5)})

                self.data[key].update({f"unpaid_last_24_hr_{currency}": round(
                    self.data[key][f"unpaid_last_24_hr_{mining_coin}"] *
                    self.data["price"][f"price_{mining_coin}"][currency], 2,)})

        logger.info(f"Data Extraction Complete")
        
    def getGauges(self):

        GPU_LABELS = ['brand', 'model', 'name', 'bus_num']
        
        self.gauges = {
            'gpu_fan': Gauge('hiveos_gpu_fan', 'GPU Fan Speed', GPU_LABELS),
            'gpu_hash': Gauge('hiveos_gpu_hash', 'GPU Hash Rate', GPU_LABELS),
            'gpu_mem_size': Gauge('hiveos_gpu_mem', 'GPU Memory Size', GPU_LABELS),
            #'gpu_mem_type': Gauge('hiveos_gpu_mem_type', 'GPU Memory Type', GPU_LABELS),
            'gpu_power': Gauge('hiveos_gpu_power', 'GPU Power Consumption', GPU_LABELS),
            'gpu_mem_temp': Gauge('hiveos_gpu_mem_temp', 'GPU Memory Temperature', GPU_LABELS),
            'gpu_core_temp': Gauge('hiveos_gpu_core_temp', 'GPU Temperature', GPU_LABELS),
            "workers_total": Gauge('hiveos_workers_total', 'Workers Total'),
            "workers_online": Gauge('hiveos_workers_online', 'Workers Online'),
            "workers_offline": Gauge('hiveos_workers_offline', 'Workers Offline'),
            "gpus_total": Gauge('hiveos_gpus_total', 'Total GPUs'),
            "gpus_online": Gauge('hiveos_gpus_online', 'Online GPUs'),
            "gpus_offline": Gauge('hiveos_gpus_offline', 'Offline GPUs'),
            "rigs_total": Gauge('hiveos_rigs_total', 'Total Rigs'),
            "rigs_online": Gauge('hiveos_rigs_online', 'Online Rigs'),
            "rigs_offline": Gauge('hiveos_rigs_offline', 'Offline Rigs'),
            'shares_accepted': Gauge('hiveos_shares_accepted', 'Shares Accepted'),
            'shares_rejected': Gauge('hiveos_shares_rejected', 'Shares Rejected'),
            'shares_invalid': Gauge('hiveos_shares_invalid', 'Shares Invalid'),
            'shares_total': Gauge('hiveos_shares_total', 'Shares Total'),
            'shares_ratio': Gauge('hiveos_shares_ratio', 'Shares Ratio'),
            'miner_start_time': Gauge('hiveos_miner_start_time', 'Miner Start Time'),
            'miner_duration': Gauge('hiveos_mining_duration', 'Mining Duration'),
            'rigs_power': Gauge('hiveos_rigs_power', 'Rigs Power'),
            "accepted_share_rate": Gauge('hiveos_accepted_share_rate', 'Accepted Share Rate (ASR)'),
            "miner_dayreward_number": Gauge("miner_dayreward_number", "24hnumreward"),
            "miner_dayreward": Gauge("miner_dayreward", "24hreward"),
            "miner_currentHashrate": Gauge("miner_hashrate_current", "currentHashrate"),
            "miner_reportedHashrate": Gauge("miner_hashrate_reported", "reportedHashrate"),
            "miner_current_luck": Gauge("miner_current_luck", "currentLuck"),
            "miner_averageHashrate": Gauge("miner_averageHashrate", "averageHashrate"),
            "miner_payments_total": Gauge("miner_payments_total", "paymentsTotal"),
            "miner_round_shares": Gauge("miner_round_shares", "roundShares"),
            "miner_shares_stale": Gauge("miner_shares_stale", "sharesStale"),
            "miner_shares_valid": Gauge("miner_shares_valid", "sharesValid"),
            "miner_workersOffline": Gauge("miner_workersOffline", "workersOffline"),
            "miner_workersOnline": Gauge("miner_workersOnline", "workersOnline"),
            "miner_workersTotal": Gauge("miner_workersTotal", "workersTotal"),
            "miner_current_balance": Gauge("miner_current_balance", "stats_balance"),
            
            f"jsonstats_price_{base_coin}": Gauge(
                f"jsonstats_price_{base_coin}", f"price_{base_coin}"),
            
            f"jsonstats_price_{mining_coin}": Gauge(
                f"jsonstats_price_{mining_coin}", f"price_{mining_coin}"),
            
            f"jsonstats_unpaid_balance_{mining_coin}": Gauge(
                f"jsonstats_unpaid_balance_{mining_coin}", f"unpaid_balance_{mining_coin}"),
            
            f"jsonstats_unpaid_balance_{currency}": Gauge(
                f"jsonstats_unpaid_balance_{currency}", f"unpaid_balance_{currency}"),
            
            f"jsonstats_unpaid_last_24_hr_{mining_coin}": Gauge(
                f"jsonstats_unpaid_last_24_hr_{mining_coin}", f"unpaid_last_24_hr_{mining_coin}"),
            
            f"jsonstats_unpaid_last_24_hr_{currency}": Gauge(
                f"jsonstats_unpaid_last_24_hr_{currency}", f"unpaid_last_24_hr_{currency}"),
            
            f"jsonstats_wallet_balance_{base_coin}": Gauge(
                f"jsonstats_wallet_balance_{base_coin}", f"wallet_balance_{base_coin}"),
            
            f"jsonstats_wallet_balance_{currency}": Gauge(
                f"jsonstats_wallet_balance_{currency}", f"wallet_balance_{currency}"),
            
            f"jsonstats_power_cost_{currency}": Gauge(
                f"jsonstats_power_cost_{currency}", f"power_cost_{currency}"),
            
            "jsonstats_mining_profitability": Gauge(
                "jsonstats_mining_profitability", "mining_profitability"),
            
            "jsonstats_mining_profitability_percent": Gauge(
                "jsonstats_mining_profitability_percent", "mining_profitability_percent")
        }
    def set_hive(self):
        logger.info(f"Setting Hive Data")
    
        farm = self.data["hive"]["farm"]
        stats = farm["stats"]
        self.gauges[f"workers_total"].set(stats["workers_total"])
        self.gauges[f"workers_online"].set(stats["workers_online"])
        self.gauges[f"workers_offline"].set(stats["workers_offline"])
        self.gauges[f"gpus_total"].set(stats["gpus_total"])
        self.gauges[f"gpus_online"].set(stats["gpus_online"])
        self.gauges[f"gpus_offline"].set(stats["gpus_offline"])
        self.gauges[f"rigs_total"].set(stats["rigs_total"])
        self.gauges[f"rigs_online"].set(stats["rigs_online"])
        self.gauges[f"rigs_offline"].set(stats["rigs_offline"])
        self.gauges[f"rigs_power"].set(stats["rigs_power"])
        self.gauges[f"accepted_share_rate"].set(stats["asr"])

        self.gauges[f"jsonstats_power_cost_{currency}"].set(
            farm[f"power_cost_{currency}"])

        self.gauges[f"jsonstats_mining_profitability"].set(
            farm["mining_profitability"])

        self.gauges[f"jsonstats_mining_profitability_percent"].set(
            farm["mining_profitability_percent"])

        # set gpu data
        worker = self.data['hive']['worker']
        for x in worker['gpu_stats']:
            lables = dict(
                brand=list(filter(lambda d: d['bus_number'] in [x['bus_num']], worker['gpu_info']))[0]['brand'],
                model=list(filter(lambda d: d['bus_number'] in [x['bus_num']], worker['gpu_info']))[0]['model'],
                name=list(filter(lambda d: d['bus_number'] in [x['bus_num']], worker['gpu_info']))[0]['short_name'],
                bus_num=x['bus_num'])
    
            self.gauges['gpu_fan'].labels(**lables).set(x['fan'])
            self.gauges['gpu_hash'].labels(**lables).set(x['hash'])
            self.gauges['gpu_power'].labels(**lables).set(x['power'])
            self.gauges['gpu_core_temp'].labels(**lables).set(x['temp'])
            self.gauges['gpu_mem_temp'].labels(**lables).set(x['memtemp'])
            self.gauges['gpu_mem_size'].labels(**lables).set(
                list(filter(lambda d: d['bus_number'] in [x['bus_num']], worker['gpu_info']))[0]['details']['mem_gb'])
            """
            self.gauges['gpu_mem_type'].labels(**lables).set(
                list(filter(lambda d: d['bus_number'] in [x['bus_num']],
                            self.data['hive']['worker']['gpu_info']))[0]['details']['mem_type'])
            """

        hashrates = worker["miners_summary"]["hashrates"][0]
        shares = hashrates["shares"]
        self.gauges[f"shares_accepted"].set(shares["accepted"])
        self.gauges[f"shares_rejected"].set(shares["rejected"])
        self.gauges[f"shares_invalid"].set(shares["invalid"])
        self.gauges[f"shares_total"].set(shares["total"])
        self.gauges[f"shares_ratio"].set(shares["ratio"])
        self.gauges[f"miner_start_time"].set(worker["stats"]["miner_start_time"])
        self.gauges[f"miner_duration"].set(int(time.time() - worker["stats"]["miner_start_time"]))

    def set_price(self):
        logger.info(f"Setting Price Data")
        self.gauges[f"jsonstats_price_{base_coin}"].set(
            self.data["price"][f"price_{base_coin}"][currency])
            
        self.gauges[f"jsonstats_price_{mining_coin}"].set(
            self.data["price"][f"price_{mining_coin}"][currency])

    def set_2miners(self):
        logger.info(f"Setting 2miners Data")
        two_miners = self.data["2miners"]
        self.gauges[f"miner_current_luck"].set(two_miners["currentLuck"])
        self.gauges[f"miner_averageHashrate"].set(two_miners["hashrate"])
        self.gauges[f"miner_payments_total"].set(two_miners["paymentsTotal"])
        self.gauges[f"miner_round_shares"].set(two_miners["roundShares"])
        self.gauges[f"miner_shares_valid"].set(two_miners["sharesValid"])
        self.gauges[f"miner_shares_stale"].set(two_miners["sharesStale"])
        self.gauges[f"miner_dayreward_number"].set(two_miners["24hnumreward"])
        self.gauges[f"miner_dayreward"].set(two_miners["24hreward"])
        self.gauges[f"miner_workersOffline"].set(two_miners["workersOffline"])
        self.gauges[f"miner_workersOnline"].set(two_miners["workersOnline"])
        self.gauges[f"miner_workersTotal"].set(two_miners["workersTotal"])
        
        self.gauges[f"jsonstats_unpaid_balance_{mining_coin}"].set(
            self.data["2miners"][f"unpaid_balance_{mining_coin}"])
        
        self.gauges[f"jsonstats_unpaid_balance_{currency}"].set(
            self.data["2miners"][f"unpaid_balance_{currency}"])
        
        self.gauges[f"jsonstats_unpaid_last_24_hr_{mining_coin}"].set(
            self.data["2miners"][f"unpaid_last_24_hr_{mining_coin}"])
        
        self.gauges[f"jsonstats_unpaid_last_24_hr_{currency}"].set(
            self.data["2miners"][f"unpaid_last_24_hr_{currency}"])
        
        self.gauges[f"miner_currentHashrate"].set(
            self.data["2miners"]["currentHashrate"])
        
        self.gauges[f"miner_reportedHashrate"].set(
            self.data["2miners"]["workers"][f"{name}"]["rhr"])
        
        self.gauges[f"miner_current_balance"].set(
            self.data["2miners"]["stats"]["balance"])

    def set_balance(self):
        logger.info(f"Setting Balance Data")
        self.gauges[f"jsonstats_wallet_balance_{base_coin}"].set(
            self.data["balance"][f"wallet_balance_{base_coin}"])
    
        self.gauges[f"jsonstats_wallet_balance_{currency}"].set(
            self.data["balance"][f"wallet_balance_{currency}"])

    def setMetrics(self):
        logger.info(f"Begin Setting Metrics data...")
        self.set_price()
        self.set_balance()
        self.set_2miners()
        self.set_hive()
        logger.info(f"Metrics Set Successfully.")

    def powerConversion(self, wattage):
        # converts a given wattage to daily cost
        kwh = wattage * 24 / 1000  # 24 hrs
        cents = 100
        return kwh * electric / cents

    def priceURL(self, coin, currency):
        return f"https://min-api.cryptocompare.com/data/price?fsym={coin}&tsyms={currency}&api_key={cc_key}"

    def writeFile(self):
        logger.info(f"Writing Results Data for JSON API...")
        with open("results.json", "w") as file:
            json.dump(self.data, file, indent=4)
        logger.info("Results Data Write Complete")


# Base Python HTTP Server to serve full json api
class JSON_API(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
    
    def do_HEAD(self):
        self._set_headers()
    
    # GET sends back a Hello world message
    def do_GET(self):
        self._set_headers()
        with open('results.json', 'r') as f:
            self.wfile.write(f.read().encode('utf-8'))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("log_file.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    # init exporter object
    exporter = PromExporter()

    # init json api server
    json_server = HTTPServer(('0.0.0.0', api_port), JSON_API)

    jobs = {
        'Exporter': threading.Thread(target=exporter.executeProcess),
        'API': threading.Thread(target=json_server.serve_forever)
    }

    # start prom http service for /metrics
    start_http_server(exporter_port)

    # kickoff jobs
    for job in jobs.values():
        job.start()

if __name__ == "__main__":
    main()
