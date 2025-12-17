aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 656008069461.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 --provenance=false -t pdfquery-agent-lambda-production -f agent.Dockerfile . 

docker tag pdfquery-agent-lambda-production:latest 656008069461.dkr.ecr.us-east-1.amazonaws.com/pdfquery-agent-lambda-production:latest

docker push 656008069461.dkr.ecr.us-east-1.
amazonaws.com/pdfquery-agent-lambda-production:latest