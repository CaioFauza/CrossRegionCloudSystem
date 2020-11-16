import boto3
import time

credentials = boto3.Session()
session = credentials.get_credentials()

ec2_east2 = boto3.client('ec2', region_name='us-east-2')  # Ohio
rds = boto3.client('rds', region_name='us-east-2')  # Ohio
ec2_east1 = boto3.resource('ec2', region_name='us-east-1')  # North Virginia
ec2_east1_client = boto3.client('ec2', region_name='us-east-1')
lb = boto3.client('elbv2', region_name='us-east-1')
auto_scaling = boto3.client('autoscaling', region_name='us-east-1')

# ======================================== Destroy ========================================================
try:  
    # db region destroy
    rds.delete_db_instance(DBInstanceIdentifier='caio-project', SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
    print("Waiting for rds elimination. Please wait, could take up to 5 minutes...")
    rds_waiter = rds.get_waiter('db_instance_deleted')
    rds_waiter.wait(DBInstanceIdentifier='caio-project')
    ec2_east2.delete_security_group(GroupName='caio-project-db-sg')
    
    
    print("RDS deleted.")

    # webserver region destroy
    print("Waiting for webserver elimination....")
    auto_scaling.delete_auto_scaling_group(AutoScalingGroupName='project-caio-ASG', ForceDelete=True)
    lb_destroy = lb.describe_load_balancers(
        Names=['project-caio-elb']
    )
    lb.delete_load_balancer(LoadBalancerArn=lb_destroy['LoadBalancers'][0]['LoadBalancerArn'])
    lb_waiter = lb.get_waiter('load_balancers_deleted')
    lb_waiter.wait(Names=['project-caio-elb'])

    tg_destroy = lb.describe_target_groups(Names=['project-caio-tg'])
    lb.delete_target_group(TargetGroupArn=tg_destroy['TargetGroups'][0]['TargetGroupArn'])

    auto_scaling.delete_launch_configuration(LaunchConfigurationName='project-caio-lc-webserver')

    image_info = ec2_east1_client.describe_images(Filters=[
        {
            'Name': 'description',
            'Values': [
                'Caio project webserver image'
            ]
        }
    ])
    
    ec2_east1_client.deregister_image(ImageId=image_info['Images'][0]['ImageId'])
    ec2_east1_client.delete_security_group(GroupName='caio-project-wb-sg')
    print("Webserver deleted.")
except:
    pass

# ======================================== Security Groups ================================================
print("Creating database security group...")
psql_sg = ec2_east2.create_security_group(
    Description='caio-project db sg',
    GroupName='caio-project-db-sg')

ec2_east2.authorize_security_group_ingress(
    GroupId=psql_sg['GroupId'],
    IpProtocol='tcp',
    FromPort=5432,
    ToPort=5432,
    CidrIp='0.0.0.0/0'
)
print("Database security group sucessfully created.")

print("Creating webserver security group...")
webserver_sg = ec2_east1_client.create_security_group(
    Description='caio-project webserver sg',
    GroupName='caio-project-wb-sg')

ec2_east1_client.authorize_security_group_ingress(
    GroupId=webserver_sg['GroupId'],
    IpProtocol='tcp',
    FromPort=8080,
    ToPort=8080,
    CidrIp='0.0.0.0/0'
)

ec2_east1_client.authorize_security_group_ingress(
    GroupId=webserver_sg['GroupId'],
    IpProtocol='tcp',
    FromPort=80,
    ToPort=80,
    CidrIp='0.0.0.0/0'
)
print("Web server security group sucessfully created.")

# ============================================ RDS ========================================================
print("Creating RDS. Please wait, could take up to 5 minutes...")
psql = rds.create_db_instance(
    DBInstanceIdentifier='caio-project',
    DBName='tasks',
    DBInstanceClass='db.t2.micro',
    VpcSecurityGroupIds=[psql_sg['GroupId']],
    Engine='postgres',
    Port=5432,
    MasterUsername='cloud',
    MasterUserPassword='cloud12345',
    AllocatedStorage=5,
    BackupRetentionPeriod=0,
    Tags=[
        {
            'Key': 'caio',
            'Value': 'project'
        }
    ]
)
waiter = rds.get_waiter('db_instance_available')
waiter.wait(
    DBInstanceIdentifier='caio-project'
)

psql_info = rds.describe_db_instances(
    DBInstanceIdentifier='caio-project'

)
print("RDS succesfully created.")
rds_ip = psql_info['DBInstances'][0]['Endpoint']['Address']
print("RDS public ip is " + str(psql_info['DBInstances'][0]['Endpoint']['Address']))

# ============================================ WebServer ==================================================
print("Creating EC2 First Instance...")

webserver_install = '''#!/bin/bash
cd home/ubuntu
sudo apt update && sudo apt upgrade -y
git clone https://github.com/CaioFauza/tasks.git
cd tasks
sudo sed -i 's/-/{}/' portfolio/settings.py
chmod +x install.sh
./install.sh
sudo reboot 
'''.format(rds_ip)

ec2_east1.create_instances(
    UserData= webserver_install,
    MinCount= 1,
    MaxCount = 1,
    InstanceType= 't2.micro',
    ImageId='ami-00ddb0e5626798373',
    KeyName='caio',
    TagSpecifications=[
        {
            'ResourceType': 'instance',
            'Tags':[
                {
                    'Key': 'caio',
                    'Value': 'project'
                }
            ]
        }
    ]
)
web_server = ec2_east1_client.describe_instances(
    Filters=[
        {
            'Name': 'instance-state-name',
            'Values': ['pending','running']
        },
        {
            'Name': 'tag:caio',
            'Values': [
                'project'
            ]
        }
    ]
)
webserver_id = web_server['Reservations'][0]['Instances'][0]['InstanceId']

waiter_ec2 = ec2_east1_client.get_waiter('instance_running')
waiter_ec2.wait(InstanceIds=[webserver_id])

waiter_ec2_ok = ec2_east1_client.get_waiter('instance_status_ok')
waiter_ec2_ok.wait(InstanceIds=[webserver_id])
print("Application ready.")

print('Creating ec2 image for webserver....')
ec2_east1_client.create_image(
    InstanceId=webserver_id,
    Name='caio-project-server',
    Description='Caio project webserver image'

)

image_information = ec2_east1_client.describe_images(
    Filters=[
        {
            'Name': 'name',
            'Values': ['caio-project-server']
        }
    ]
)

image_id = image_information['Images'][0]['ImageId']
image_waiter = ec2_east1_client.get_waiter('image_available')
image_waiter.wait(ImageIds=[image_id])
print('Ec2 image created.')

print("Terminating first instance...")
ec2_east1_client.terminate_instances(InstanceIds=[webserver_id])

waiter_ec2_terminated = ec2_east1_client.get_waiter('instance_terminated')
waiter_ec2_terminated.wait(InstanceIds=[webserver_id])
print("First instance terminated.")

print("Creating launch_configuration...")
auto_scaling.create_launch_configuration(
    LaunchConfigurationName='project-caio-lc-webserver',
    ImageId = image_id,
    SecurityGroups= [webserver_sg['GroupId']],
    InstanceType= 't2.micro'
)
print('Launch configuration created.')

print('Creating Elastic Load Balancer..')
subnets = ec2_east1_client.describe_subnets()
load_balancer = lb.create_load_balancer(
    Name='project-caio-elb',
    SecurityGroups=[webserver_sg['GroupId']],
    Type='application',
    Subnets=[subnets['Subnets'][0]['SubnetId'], subnets['Subnets'][1]['SubnetId'], subnets['Subnets'][2]['SubnetId'], subnets['Subnets'][3]['SubnetId'], subnets['Subnets'][4]['SubnetId'], subnets['Subnets'][5]['SubnetId']]
    )
print('Elastic Load Balancer created.')

print("Creating target group...")
vpc_info = ec2_east1_client.describe_vpcs()
target_group= lb.create_target_group(
    Name="project-caio-tg",
    Protocol='HTTP',
    TargetType='instance',
    Port=8080,
    VpcId=vpc_info['Vpcs'][0]['VpcId'],
    HealthCheckProtocol='HTTP',
    HealthCheckEnabled=True,
    HealthCheckPath='/',
    HealthCheckPort='traffic-port',
    HealthCheckIntervalSeconds=30,
    HealthCheckTimeoutSeconds=5,
    HealthyThresholdCount=5,
    UnhealthyThresholdCount=5,
    Matcher={
        'HttpCode': '200'
    }
)
print("Target group created.")

print("Creating Load Balancer Listener...")
lb.create_listener(
    LoadBalancerArn=load_balancer['LoadBalancers'][0]['LoadBalancerArn'],
    Protocol='HTTP',
    Port=80,
    DefaultActions=[
        {
            'Type': 'forward',
            'TargetGroupArn': target_group['TargetGroups'][0]['TargetGroupArn'],


        }
    ]
)
print("Load Balancer listener created.")

print("Creating Auto Scaling group...")
auto_scaling.create_auto_scaling_group(
    AutoScalingGroupName="project-caio-ASG",
    LaunchConfigurationName="project-caio-lc-webserver",
    MinSize=1,
    MaxSize=5,
    DesiredCapacity=1,
    AvailabilityZones=['us-east-1a', 'us-east-1b', 'us-east-1c', 'us-east-1d', 'us-east-1e', 'us-east-1f'],
    Tags=[
        {
            'Key': 'caio',
            'Value': 'project'
        }
    ]
)
print("Auto Scaling group created.")

print("Attaching load balancer to Auto Scaling Group...")

auto_scaling.attach_load_balancer_target_groups(
    AutoScalingGroupName='project-caio-ASG',
    TargetGroupARNs=[target_group['TargetGroups'][0]['TargetGroupArn']]
)

print("Load Balancer attached to Auto Scaling Group.")

print("Adding scaling policy to Auto Scaling group...")

load_balancer_id = load_balancer['LoadBalancers'][0]['LoadBalancerArn'].split("loadbalancer/")[1]
target_group_id = target_group['TargetGroups'][0]['TargetGroupArn'].split(":")[5]
scale_policy_label = (str(load_balancer_id) + "/" + str(target_group_id))

auto_scaling.put_scaling_policy(
    AutoScalingGroupName="project-caio-ASG",
    PolicyName='resize-request-counter',
    PolicyType='TargetTrackingScaling',
    EstimatedInstanceWarmup=10,
    TargetTrackingConfiguration={
        'PredefinedMetricSpecification': {
            'PredefinedMetricType': 'ALBRequestCountPerTarget',
            'ResourceLabel': scale_policy_label
        },
        'TargetValue': 5
        
    },
    Enabled=True
)
print("Scaling policy added.")

print("Waiting for Load Balancer to be ready. Please wait, could take up to 3 minutes...")
elb_waiter = lb.get_waiter('load_balancer_available')
elb_waiter.wait(Names=['project-caio-elb'])
print("Load Balancer public ip is " + str(load_balancer['LoadBalancers'][0]['DNSName']))