targetScope = 'resourceGroup'

@description('Azure region for the ACA Native DEV foundation.')
param location string = resourceGroup().location

@description('Short environment name used in resource names and EDIM_ENV.')
@allowed([
  'sdbx'
  'dev'
  'uat'
  'intg'
  'prod'
])
param edimEnvironment string = 'dev'

@description('Globally unique Azure Container Registry name, 5-50 alphanumeric characters.')
param acrName string

@description('Azure Container Apps managed environment name.')
param containerAppsEnvironmentName string

@description('Container App name for the ACA Native FastAPI host.')
param containerAppName string

@description('User-assigned identity used by the Container App to pull from ACR and access Key Vault.')
param runtimeIdentityName string

@description('Key Vault name. The vault is created without application secrets.')
param keyVaultName string

@description('Immutable image reference, preferably an ACR digest.')
param image string

@description('Existing PostgreSQL connection-string secret name in Key Vault.')
param databaseSecretName string = 'edim-database-url'

@description('Existing Foundry client secret name in Key Vault.')
param foundryClientSecretName string = 'edim-foundry-client-secret'

@description('Existing Foundry tenant/client ID secret names in Key Vault.')
param foundryTenantSecretName string = 'edim-foundry-tenant-id'
param foundryClientIdSecretName string = 'edim-foundry-client-id'

@description('Existing Log Analytics workspace resource ID. Leave empty to create one.')
param existingLogAnalyticsWorkspaceId string = ''

@description('Existing subnet resource ID for ACA VNet integration. Required for private production networking.')
param infrastructureSubnetId string = ''

@description('Use internal ingress for private environments.')
param internalIngress bool = true

@description('Minimum number of replicas.')
param minReplicas int = 1

@description('Maximum number of replicas.')
param maxReplicas int = 3

@description('Container CPU allocation.')
param containerCpu string = '0.5'

@description('Container memory allocation.')
param containerMemory string = '1Gi'

@description('Create the Container App resource. Keep false until Key Vault, PostgreSQL, networking, and image approvals are complete.')
param deployContainerApp bool = false

@description('Create a Log Analytics workspace when an existing workspace ID is not supplied.')
param createLogAnalyticsWorkspace bool = true

var logAnalyticsWorkspaceName = '${containerAppsEnvironmentName}-law'
var keyVault = resourceId('Microsoft.KeyVault/vaults', keyVaultName)
var acrPullRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)
var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)
var logAnalyticsWorkspaceId = empty(existingLogAnalyticsWorkspaceId)
  ? resourceId('Microsoft.OperationalInsights/workspaces', logAnalyticsWorkspaceName)
  : existingLogAnalyticsWorkspaceId
var databaseSecretUri = '${reference(keyVault, '2023-07-01', 'Full').properties.vaultUri}secrets/${databaseSecretName}'
var foundryClientSecretUri = '${reference(keyVault, '2023-07-01', 'Full').properties.vaultUri}secrets/${foundryClientSecretName}'
var foundryTenantSecretUri = '${reference(keyVault, '2023-07-01', 'Full').properties.vaultUri}secrets/${foundryTenantSecretName}'
var foundryClientIdSecretUri = '${reference(keyVault, '2023-07-01', 'Full').properties.vaultUri}secrets/${foundryClientIdSecretName}'

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = if (createLogAnalyticsWorkspace && empty(existingLogAnalyticsWorkspaceId)) {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource userAssignedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: runtimeIdentityName
  location: location
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, userAssignedIdentity.id, acrPullRoleDefinitionId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: userAssignedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
  }
}

resource keyVaultSecretsUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, userAssignedIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: vault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: userAssignedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2022-10-01').properties.customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2022-10-01').primarySharedKey
      }
    }
    vnetConfiguration: empty(infrastructureSubnetId)
      ? null
      : {
          infrastructureSubnetId: infrastructureSubnetId
          internal: internalIngress
        }
  }
  dependsOn: [
    logAnalyticsWorkspace
  ]
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = if (deployContainerApp) {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: !internalIngress
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: '${containerRegistry.name}.azurecr.io'
          identity: userAssignedIdentity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: databaseSecretUri
          identity: userAssignedIdentity.id
        }
        {
          name: 'foundry-client-secret'
          keyVaultUrl: foundryClientSecretUri
          identity: userAssignedIdentity.id
        }
        {
          name: 'foundry-tenant-id'
          keyVaultUrl: foundryTenantSecretUri
          identity: userAssignedIdentity.id
        }
        {
          name: 'foundry-client-id'
          keyVaultUrl: foundryClientIdSecretUri
          identity: userAssignedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'PORT'
              value: '8080'
            }
            {
              name: 'EDIM_ENV'
              value: edimEnvironment
            }
            {
              name: 'EDIM_STATE_STORE'
              value: 'postgres'
            }
            {
              name: 'EDIM_RECOMMENDATION_STORE'
              value: 'postgres'
            }
            {
              name: 'EDIM_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'EDIM_FOUNDRY_TENANT_ID'
              secretRef: 'foundry-tenant-id'
            }
            {
              name: 'EDIM_FOUNDRY_CLIENT_ID'
              secretRef: 'foundry-client-id'
            }
            {
              name: 'EDIM_FOUNDRY_CLIENT_SECRET'
              secretRef: 'foundry-client-secret'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output runtimeIdentityResourceId string = userAssignedIdentity.id
output runtimeIdentityPrincipalId string = userAssignedIdentity.properties.principalId
output keyVaultResourceId string = vault.id
output containerAppsEnvironmentResourceId string = containerAppsEnvironment.id
output containerAppResourceId string = deployContainerApp ? containerApp.id : ''
