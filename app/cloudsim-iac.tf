# main.tf

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "results_bucket" {
  bucket = "cloud-sim-results-bucket"
  acl    = "private"
}

resource "aws_dynamodb_table" "sim_metadata" {
  name           = "SimulationResults"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

resource "aws_security_group" "ec2_sg" {
  name        = "cloud-sim-sg"
  description = "Allow SSH and Flask access from my IP"

  ingress {
    description = "Allow SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["[IP]"]
  }

  ingress {
    description = "Allow Flask app access"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["[IP_PLACEHOLDER]"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "cloud_sim_instance" {
  ami           = "ami-0c02fb55956c7d316" 
  instance_type = "t2.micro"
  key_name      = "my-keypair"
  security_groups = [aws_security_group.ec2_sg.name]

  tags = {
    Name = "CloudSimApp"
  }
}
