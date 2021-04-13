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


def get_cpu_utilization(instance, region, days):
    """
    Gets CPU utilization for every instance
    """

    client = SESSION.client('cloudwatch', region_name=region)

    time_from = (datetime.now() - timedelta(days=days))
    time_to = datetime.now()

    response = client.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance
            },
        ],
        StartTime=time_from,
        EndTime=time_to,
        Period=(days * 86400),
        Statistics=[
            'Average',
            'Maximum'
        ],
        Unit='Percent'
    )

    print(response)

    if response['Datapoints']:
        for cpu in response['Datapoints']:
            return {'Average': cpu.get('Average', 0), 'Maximum': cpu.get('Maximum', 0)}
    else:
        return {'Average': 0, 'Maximum': 0}


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


@app.route('/', methods=['GET', 'POST'])
def main():
    regions = SESSION.get_available_regions('ec2')
    return render_template('index.html', regions=regions)


@app.route('/main_scan', methods=['GET', 'POST'])
def main_scan():
    start_time = time.time()
    execution_output = ''

    regions = [request.args.get('region', '')]

    for region in regions:
        try:
            print(f'proceeding {region}')
            region_average = []
            instances = scan_region(region)

            for instance in instances:
                cpu_utilization = get_cpu_utilization(instance["id"], region, 7)
                # calculating average only for instances with load > 0
                if cpu_utilization['Average']:
                    region_average.append(cpu_utilization['Average'])
                execution_output += f'<tr><td>{region}</td><td>{instance["id"]}</td><td>{instance["type"]}</td><td>{round(cpu_utilization["Average"], 2)}</td><td>{round(cpu_utilization["Maximum"], 2)}</td></tr>'
            if len(region_average):
                execution_output += f'<tr><td colspan="5">Average cpu utilization for the region is {round(sum(region_average)/len(region_average), 2)}%</td></tr>'

        except ClientError as exc:
            if exc.response['Error']['Code'] == "AuthFailure":
                print(f"looks like {region} is disabled, skipping")
                continue
            else:
                raise

    return render_template('main_scan.html', rseconds=round((time.time() - start_time), 2), execution_output=execution_output)
