terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

resource "aws_security_group" "dd_sg" {
  name        = "dd-security-group"
  description = "Downtime-Deniers app access"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "App/service ports (temporary, will tighten later)"
    from_port   = 5000
    to_port     = 9000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Kubernetes NodePort range"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "dd-security-group"
  }
}

resource "aws_instance" "dd_instance" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.medium"
  key_name               = "dd-key"
  iam_instance_profile   = aws_iam_instance_profile.dd_instance_profile.name
  vpc_security_group_ids = [aws_security_group.dd_sg.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Name = "downtime-deniers"
  }
}

resource "aws_eip" "dd_eip" {
  instance = aws_instance.dd_instance.id
  domain   = "vpc"
}

output "instance_public_ip" {
  value = aws_eip.dd_eip.public_ip
}

output "instance_id" {
  value = aws_instance.dd_instance.id
}

resource "aws_iam_role" "dd_ec2_role" {
  name = "dd-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dd_ecr_pull" {
  role       = aws_iam_role.dd_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "dd_s3_access" {
  role       = aws_iam_role.dd_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_iam_instance_profile" "dd_instance_profile" {
  name = "dd-instance-profile"
  role = aws_iam_role.dd_ec2_role.name
}
