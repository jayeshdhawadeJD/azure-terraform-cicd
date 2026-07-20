terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "tfstatejd2026"
    container_name        = "tfstate"
    key                    = "demo-infra.tfstate"
    use_oidc               = true
    use_azuread_auth        = true
  }
}

provider "azurerm" {
  features {}
  use_oidc = true
}

resource "azurerm_resource_group" "demo" {
  name     = "rg-portfolio-demo"
  location = "centralindia"
}