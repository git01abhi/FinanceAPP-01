import os, argparse, webbrowser
from app import app, start_scheduler, run_fetch_cycle

def main():
    parser = argparse.ArgumentParser(description='TheCoder Finance App')
    parser.add_argument('--config', default='config.json', help='config.json or config.yaml path')
    parser.add_argument('--open', action='store_true', help='Open dashboard in browser')
    args = parser.parse_args()

    # app.py reads TC_CONFIG env var on import; set it here then run
    os.environ['TC_CONFIG'] = args.config
    # First fetch cycle is run on app start; we can open browser
    if args.open:
        webbrowser.open('http://127.0.0.1:5000/')
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    main()
