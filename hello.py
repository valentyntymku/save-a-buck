#!/usr/bin/env python3.7

'''
FLASK_APP=hello.py flask run
'''
import argparse
from datetime import datetime, timedelta
import json
import time
import boto3
from botocore.exceptions import ClientError

from flask import Flask, render_template, request
app = Flask(__name__)

SESSION = boto3.Session()


def get_cpu_utilization(mqueries, region, days):
    """
    Gets CPU utilization for instances
    """

    client = SESSION.client('cloudwatch', region_name=region)

    time_from = (datetime.now() - timedelta(days=days))
    time_to = datetime.now()

    response = client.get_metric_data(
        MetricDataQueries=mqueries,
        StartTime=time_from,
        EndTime=time_to
    )

    return response['MetricDataResults']


def scan_region(region):
    """
    Gets all instances in a region
    """

    client = SESSION.client('ec2', region_name=region)

    instances = []
    paginator = client.get_paginator('describe_instances')

    for page in paginator.paginate():
        for res in page['Reservations']:
            for inst in res['Instances']:
                instance_map = {}
                instance_map["id"] = inst['InstanceId']
                instance_map["type"] = inst['InstanceType']
                instances.append(instance_map)

    print(f'Instances found: {len(instances)}')

    return instances


@app.route('/', methods=['GET'])
def main():
    regions = SESSION.get_available_regions('ec2')
    return render_template('index.html', regions=regions)


@app.route('/main_scan', methods=['GET'])
def main_scan():
    start_time = time.time()
    execution_output = ''
    days = 30
    percent = 0

    regions = [request.args.get('region', '')]

    for region in regions:
        try:
            print(f'proceeding {region}')
            region_average = []
            mqueries = []
            cpu_utilization_map = {}
            instances = scan_region(region)

            for instance in instances:
                cpu_utilization_map[instance["id"]] = {"type": instance["type"], "average": "", "maximum": ""}
                for stat in ['Average', 'Maximum']:
                    mqueries.append(
                        {
                            'Id': f'{stat.lower()}_{instance["id"].replace("i-", "")}',
                            'Label': instance["id"],
                            'MetricStat': {
                                'Metric': {
                                    'Namespace': 'AWS/EC2',
                                    'MetricName': 'CPUUtilization',
                                    'Dimensions': [
                                        {
                                            'Name': 'InstanceId',
                                            'Value': instance["id"]
                                        },
                                    ]
                                },
                                'Period': (days * 86400),
                                'Stat': stat,
                                'Unit': 'Percent'
                            }
                        },
                    )

            if mqueries:
                cpu_utilization_request = get_cpu_utilization(mqueries, region, days)
                for cpu_utilization in cpu_utilization_request:
                    # calculating average only for instances with load > 0
                    if "average" in cpu_utilization['Id']:
                        if cpu_utilization['Values']:
                            cpu_utilization_map[cpu_utilization['Label']]["average"] = cpu_utilization['Values'][0]
                            region_average.append(cpu_utilization['Values'][0])
                        else:
                            cpu_utilization_map[cpu_utilization['Label']]["average"] = 0
                    else:
                        if cpu_utilization['Values']:
                            cpu_utilization_map[cpu_utilization['Label']]["maximum"] = cpu_utilization['Values'][0]
                        else:
                            cpu_utilization_map[cpu_utilization['Label']]["maximum"] = 0

            for ec2_instance in cpu_utilization_map:
                execution_output += f'<tr class="item"><td>{region}</td><td>{ec2_instance}</td><td>{cpu_utilization_map[ec2_instance]["type"]}</td><td>{round(cpu_utilization_map[ec2_instance]["average"], 2)}</td><td>{round(cpu_utilization_map[ec2_instance]["maximum"], 2)}</td></tr>'
            if len(region_average):
                percent = round(sum(region_average)/len(region_average), 2)

        except ClientError as exc:
            if exc.response['Error']['Code'] == "AuthFailure":
                print(f"looks like {region} is disabled, skipping")
                continue
            else:
                raise

    return render_template('main_scan.html', rseconds=round((time.time() - start_time), 2), execution_output=execution_output, percent=percent)
