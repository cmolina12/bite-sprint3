# =============================================================================
# Makefile — atajos para BITE.co Sprint 3 (CloudShell del Learner Lab)
# =============================================================================
# CloudShell ya viene autenticado contra tu cuenta del lab.
# No necesitas configurar credenciales manualmente.
# =============================================================================
.PHONY: help check init plan apply apply-auto destroy output fmt validate targets-health alb-url

help: ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

check: ## Verificar que estás autenticado en AWS (CloudShell lo hace automático)
	@aws sts get-caller-identity > /dev/null 2>&1 && echo "✅ Sesión AWS activa" || (echo "❌ No estás autenticado. ¿El lab está corriendo?"; exit 1)

init: ## terraform init (primera vez)
	cd terraform && terraform init

fmt: ## Formatear código Terraform
	cd terraform && terraform fmt -recursive

validate: ## Validar sintaxis Terraform
	cd terraform && terraform validate

plan: ## terraform plan (ver qué se va a crear/modificar)
	cd terraform && terraform plan

apply: ## terraform apply (crea/actualiza la infraestructura)
	cd terraform && terraform apply

apply-auto: ## terraform apply -auto-approve (sin pedir confirmación)
	cd terraform && terraform apply -auto-approve

destroy: ## terraform destroy — IMPORTANTE: correr al final de cada sesión del lab
	cd terraform && terraform destroy

output: ## Mostrar los outputs (URLs, endpoints, IDs)
	cd terraform && terraform output

alb-url: ## Imprimir solo la URL del ALB
	@cd terraform && terraform output -raw alb_url

targets-health: ## Ver el estado de salud de las EC2 del Manejador de Reportes
	@TG_ARN=$$(cd terraform && terraform output -raw target_group_arn 2>/dev/null); \
	if [ -z "$$TG_ARN" ]; then echo "⚠️  Aún no hay Target Group desplegado"; exit 1; fi; \
	aws elbv2 describe-target-health --target-group-arn "$$TG_ARN" \
	  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Reason]' \
	  --output table
