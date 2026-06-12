# Politique de confidentialité — CelluleTrade

*Dernière mise à jour : 11/06/2026*

Cette politique explique quelles données personnelles CelluleTrade collecte, pourquoi, comment elles sont protégées, et quels sont vos droits, conformément au Règlement Général sur la Protection des Données (RGPD).

## 1. Responsable du traitement

- **Responsable** : [Prénom NOM — Auto-entrepreneur]
- **Contact (DPO / demandes RGPD)** : contact@celluletrade.com

## 2. Données collectées

| Donnée | Origine | Finalité |
|---|---|---|
| Identifiant Telegram (chat_id, nom d'utilisateur, prénom) | Fournie automatiquement par Telegram lors du `/start` | Identifier l'utilisateur, lui envoyer ses notifications |
| Clé API Binance (clé + secret) | Saisie volontaire par l'utilisateur | Consulter l'historique des dépôts de son compte Binance pour générer les notifications |
| Adresse de wallet Rise (Arbitrum) | Saisie volontaire par l'utilisateur | Surveiller les dépôts entrants sur ce wallet |
| Données d'abonnement (plan, statut, identifiants Stripe) | Générées lors de la souscription | Gérer l'accès au service et la facturation |
| Dernier identifiant de transaction Binance/Rise notifié | Générée par le système | Éviter les notifications en double |

## 3. Stockage et sécurité

- Les clés API Binance et le secret associé sont **chiffrés au repos** (chiffrement symétrique Fernet) dans la base de données. Ils ne sont jamais affichés en clair après saisie.
- L'accès à la base de données est restreint à l'exploitant du service.
- Aucune donnée de carte bancaire n'est stockée par CelluleTrade : les paiements sont gérés directement par Stripe.

## 4. Hébergement

Les données sont hébergées sur les serveurs du fournisseur d'infrastructure utilisé pour exécuter le bot (actuellement Render). Aucune donnée n'est vendue ou partagée à des fins commerciales avec des tiers.

## 5. Destinataires des données

- **Telegram** : reçoit les messages envoyés par le bot (notifications) — voir la politique de confidentialité de Telegram.
- **Binance / Alchemy (Rise)** : interrogés en lecture seule via les identifiants fournis, pour détecter les dépôts.
- **Stripe** : traite les paiements et reçoit les informations nécessaires à la facturation (aucune donnée de carte n'est transmise à CelluleTrade).

## 6. Durée de conservation

Les données sont conservées tant que le compte est actif. En cas de suppression de compte (voir document dédié), les données personnelles et les identifiants API sont supprimés de la base de données.

## 7. Vos droits

Conformément au RGPD, vous disposez des droits suivants :
- **Droit d'accès** : obtenir une copie des données vous concernant.
- **Droit de rectification** : corriger des données inexactes.
- **Droit à l'effacement** : demander la suppression de votre compte et de vos données (voir document "Suppression de compte").
- **Droit à la portabilité** : recevoir vos données dans un format structuré.
- **Droit d'opposition / limitation** : vous opposer à un traitement ou en demander la limitation.

Pour exercer ces droits, contactez : **contact@celluletrade.com**. Une réponse sera apportée dans un délai maximum d'un mois.

## 8. Mineurs

Le service n'est pas destiné aux personnes mineures.

## 9. Modifications

Cette politique peut être mise à jour. Les utilisateurs seront informés de tout changement substantiel via le bot Telegram.
