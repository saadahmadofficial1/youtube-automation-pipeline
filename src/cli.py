import argparse
import json
from pathlib import Path
from .pipeline import Pipeline, load_config

def main():
    parser = argparse.ArgumentParser(description='Local video orchestration demo')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('new').add_argument('topic')
    run = sub.add_parser('run'); run.add_argument('job_id'); run.add_argument('--smoke', action='store_true', required=True)
    sub.add_parser('upload').add_argument('job_id')
    args = parser.parse_args()
    pipeline = Pipeline(Path.cwd(), load_config(Path('config/pipeline.json')))
    if args.command == 'new': result = pipeline.create_job(args.topic)
    elif args.command == 'run': result = pipeline.run(args.job_id, smoke=True)
    else: result = pipeline.upload(args.job_id)
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
