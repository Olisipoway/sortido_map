import subprocess
import json
import csv
import time
import os
import random
from datetime import datetime, timezone

# Refresh cookies when jwt-session expires (~24h) or cf_clearance expires
# merchants.ubereats.com → DevTools → Network → any graphql request → Headers → copy cookie value
COOKIES = '_ua={"session_id":"714a653e-91fc-4cc7-9170-570d076b265e","session_time_ms":1792424281094}; marketing_vistor_id=05db5157-9ca1-4a1a-afc1-6b8ae07bc775; user_city_ids=52; uev2.gg=true; u-cookie-prefs=eyJ2ZXJzaW9uIjoxMDAsImRhdGUiOjE3OTI0MjQyODI3NzYsImNvb2tpZUNhdGVnb3JpZXMiOlsiZXNzZW50aWFsIl0sImltcGxpY2l0IjpmYWxzZX0%3D; UBER_CONSENTMGR=1792424282776|consent:false; udi-id=yxzuLPN0NhIzScWFcrK2nas7qYVUMqAwhlGEGuV9NuhxjTLG2FkymPjY6tXwwaRnQEgrluw2Hnp2hCeOqkivT9IF3XLQjQTLLH+ujx00bjAWMnqbBSfDb5UGN8xlL1Rqkuq6SxuySUq0XiCyCSslexWPG8Xc1Z5UozhPiF4Xp9ZOuWRsMhukZWiXWQsVD8I/woKOBCVgig4ifQHm1FmIag==8gTMtv/QDZpMrG43PHG+yQ==/W6LxE+IPMO3EbS0AOOp+r0H+jCr2OU29mVvuNx7kXM=; _cc=AXHZWoMWF49eWI7zgb%2FsPBcG; rateLimiterCookieSession={"rateLimitingID":"62eb8902-a015-4042-9b6c-4c2e08eff415"}; sid=QA.CAESEBfV2Co_YEAOpnogjheYVyoYw-OR3gYiATEqJDYyNGQ3ZDJmLTlhM2UtNDBlOC04ZDg1LTdhYTc1YTI4MDAyNjI8vtNsakjQzfrIAz_oYME1ewAobHKJRQQrWSFpuinR6A1WQgXrbvYsw--lCZPrMGan0k0KmTW2iOvibTu4OgExQg0udWJlcmVhdHMuY29t.3F87RH8q7we9nPJkwZ53j-jwAP634lrhDjwklkCT0uA; smeta={expiresAt:1808036291486}; selectedRestaurant=755282a8-7d8f-51aa-a570-86867606e6c4; UNIFIED_ADMIN_PORTAL_USER_CITY_ID=[52]; uber_sites_geolocalization={%22best%22:{%22localeCode%22:%22en%22%2C%22countryCode%22:%22PT%22%2C%22territoryGeoPoint%22:{%22latitude%22:38.713811%2C%22longitude%22:-9.139386}%2C%22territoryId%22:52%2C%22territoryName%22:%22Lisbon%22%2C%22territorySlug%22:%22lisbon%22}%2C%22url%22:{%22localeCode%22:%22en%22%2C%22countryCode%22:%22PT%22}%2C%22user%22:{%22geoIpCoordinates%22:{%22lat%22:38.7219%2C%22lng%22:-9.1398}%2C%22expiresAt%22:%222026-10-27T12:13:44.522Z%22%2C%22countryCode%22:%22PT%22%2C%22territoryId%22:52%2C%22productGeofenceUUID%22:%22cfb47129-a208-4c39-b8a1-054870b23994%22%2C%22territoryGeoJson%22:[[{%22lat%22:39.31773%2C%22lng%22:-9.579847}%2C{%22lat%22:39.31773%2C%22lng%22:-8.4909782}%2C{%22lat%22:38.3474598%2C%22lng%22:-8.4909782}%2C{%22lat%22:38.3474598%2C%22lng%22:-9.579847}]]%2C%22territoryGeoPoint%22:{%22latitude%22:38.713811%2C%22longitude%22:-9.139386}%2C%22territorySlug%22:%22lisbon%22%2C%22territoryName%22:%22Lisbon%22%2C%22localeCode%22:%22en%22}}; udi-dd-aia=Ixyf6DNrCSz/glbzIpT7m0rHNlZVOnBmRYuKhinaMDiyioye/Q/DjQi1hwEBMBT6AubPfLb8TBw4HpWezjatm7f3XBBRiINLxsCnj19PUAbiFHj4p9kyTzZ8DNDDhXwMtTijAUs2zGYfUSvHssRaqY01G4htubHel5wgyVgTUNq9obTegQ3fnmcJkphVo6CQJBLmZDiYWN2++x07dIBqG17ZlXEk6j1Eq/lPgG32XQP130/uBC4RGETFtQ8dKOuINFXNYfHeXJI55fhj/C2SYejZz5/05d098NRvq07pOqg7GyfHPKo0GPPoZXmTpBKG0y9Nf4vNsQg6rZQYVWGxU6m3OscHi0BbAYFIr3hqJ2vTMmEkDFLSiUnPSfmXTOzuXHnFknaYMvVIt2ypGngubVFP04M+IqVceuqOT4EYVaHP/B9wYvtOQV3ZLVp0aw7gMBOliy3xk6chekBm/35HgQ==5CwNU9i843lMTflTKAiXGIL8cYaGvZZe0yNE6cdRx3M=; uev2.id.xp=81c88be4-2081-437b-9dac-ef9c9179a2dc; dId=d2255c49-c940-433d-b3ed-c610b108f3a3; uev2.gdprAdsConsented=true; uev2.loc=%7B%22address%22%3A%7B%22address1%22%3A%22Miraflores%22%2C%22address2%22%3A%22Linda-a-Velha%22%2C%22aptOrSuite%22%3A%22%22%2C%22eaterFormattedAddress%22%3A%22Miraflores%2C%20Linda-a-Velha%2C%20Portugal%22%2C%22subtitle%22%3A%22Linda-a-Velha%22%2C%22title%22%3A%22Miraflores%22%2C%22uuid%22%3A%22%22%7D%2C%22latitude%22%3A38.714021599999995%2C%22longitude%22%3A-9.2350551%2C%22reference%22%3A%22ChIJD0_kcH3MHg0RDUd4BwqB3d8%22%2C%22referenceType%22%3A%22google_places%22%2C%22type%22%3A%22google_places%22%2C%22addressComponents%22%3A%7B%22city%22%3A%22Linda-a-Velha%22%2C%22countryCode%22%3A%22PT%22%2C%22firstLevelSubdivisionCode%22%3A%2211%22%2C%22postalCode%22%3A%22%22%7D%2C%22categories%22%3A%5B%22NEIGHBORHOOD%22%2C%22CITY___TOWN%22%2C%22AREAS_AND_BUILDINGS%22%2C%22LANDMARK%22%2C%22geography%22%5D%2C%22originType%22%3A%22user_autocomplete%22%2C%22source%22%3A%22manual_auto_complete%22%2C%22userState%22%3A%22FirstTimeEater%22%2C%22residenceType%22%3A%22%22%7D; uev2.do=c08e1826-6a35-4cfa-80d8-9093f4b6d508; jwt-session=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3OTM2NTYzMTIsImV4cCI6MTc5Mzc0MjcxMn0.g9HI7cDT2vSKofaH3urLRI_NIhDwGtDFPzJTJw2Mh0A; udi-fingerprint=nCq1Jpmp4hXtxuyrM4bisILJKFK35GPOIGN+EG2LWzwAoJ0ivGNGTilrrh7KVHFyK8Rxk7r9RGC2w80Q2Z8hZw==aemoGUBjX8SxZQZfBkaDEN+zgu+JqkKKxIfI2UKOfYE=; _iidt=SA2aKgHY7rPgFJ7JRf7znRHj18vBCgIexms9ogRZS2jzVUlKSLq0/8MOKjX1/SXAsVfAJ9NsKG82b6CtUSyFwdkrpuQrd9iPvEpb2+Y=; _vid_t=IIyul8vLbHh5Gb1darCf7AW8qHDuKd1To2rd7vsmKRknVjLpKmnYK1PcxwSTBcNLWePCjJ0vRqBB9WuZLhzPlwb4kJHEu/B5pKyEvVc=; udi-dd-fjs=jwKpqlL6mGZunDqH8gVatLANPsS8EkNgu9Y9Fdqv1azT8w9sWEPkHWGTxHwRqOGR5Mbiane7JKzPWFE4bO6coPkoZRXT8AihYy8PncPJz1r4YOWdssuZLDumJTDhobTsYIpvrheusgvd+K5FWEx+VzkPeseHThokUtI2qyJiaB1DhPZFj3ze8U0vlqjQ8eqjBtAi+xNhyswpYzSn05dbKc5AZWOn3AE8n5hrAnWU8zHpxCEns4zj9ohAhgG3DK1Jln1mPGHJhwVHOP7qFI/uUYW9gUOCs84ruONQQ00JrVRb9JDJ+5P8zPJzIDBqpBfi7WhHXdJFvdclK+lTbOPGxH0f2qOXfxp15BayfaJOXMItQTCovYNfeuhxDnZy4PqEwdRRVPg+fQXfzZYh1RvYixElUtWaPwSTEtWUPND0mYQ=bKh+7R7I9uFxmMNtUOGpnQ==5LPGCp1M1/fDmOkLHP+LMFlHT8DHlInAFVJbgbRZVn4=; jwt-session-uem=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7InNsYXRlLWV4cGlyZXMtYXQiOjE3OTM3MjMyOTg0NDB9LCJpYXQiOjE3OTM3MTg5MzMsImV4cCI6MTc5NDMyMzczM30.hQmy3dwNJVO5Dvm-edpw2glWbHriloMkgJkUq_Wjiqc; mp_adec770be288b16d9008c964acfba5c2_mixpanel=%7B%22distinct_id%22%3A%20%22624d7d2f-9a3e-40e8-8d85-7aa75a280026%22%2C%22%24device_id%22%3A%20%221a158627d7f33d-033dfdc64ca5c58-1a525630-384000-1a158627d803344%22%2C%22%24initial_referrer%22%3A%20%22https%3A%2F%2Fmerchants.ubereats.com%2F%22%2C%22%24initial_referring_domain%22%3A%20%22merchants.ubereats.com%22%2C%22%24user_id%22%3A%20%22624d7d2f-9a3e-40e8-8d85-7aa75a280026%22%2C%22%24search_engine%22%3A%20%22google%22%7D; cf_clearance=CoUfU5EiK009Rf0Q-72-AnB7P5yXQukbcE8PFPeGAqZigPtj2Fc4ba2Mv1mwVJHOo9DINbz7vL8Q4y6Pi2EmWNJJRLItKZR-wPHD8yRL9fJCKJKELAAbThjmSe1XoyPPHuZdy-DJMrTl4KJgzFZUhfuEQD_INeQ7PBeskE3K1Ezv_ZCJ0m9v-8IgShv582BxYVcyWTqGEhxWq1ft_vIkgD6E03FbXdk4EKOxcMenWPi9VcJ34sBHuBew5ct6hucBQV8VkUCYvqohIqi_rl26GHeGq-0sARHNFdeFCdywv9sbqswZObP0gnD9; __cf_bm=M2FGFoN.nQp84KkWcq16sPZRh3wczmdlU0f_v6IMbsQ-1793721502.199533-1.0.1.1-e57HdOs3I85f6Ut6w7zTqLVD8US66ysEbm8kSVqq7mhuqW0HFuDSWQ79lPF02KW9yWBt2OraiAcT80RaDEBuyFe43Ln1uifW3aEToUgoSbCCkIgWCrGcNvVFK2Gptgsq'

STORE_UUID = "755282a8-7d8f-51aa-a570-86867606e6c4"
API_URL    = "https://merchants.ubereats.com/manager/graphql"

LIST_ORDERS_QUERY = """
query ordersV2($filters: Orders_OrdersFiltersInput!, $pagination: Orders_OrdersPaginationInput, $shouldEnableChargebackComms: Boolean, $operationMetricsUDLFlowEnabled: Boolean) {
  ordersV2(filters: $filters, pagination: $pagination, shouldEnableChargebackComms: $shouldEnableChargebackComms, operationMetricsUDLFlowEnabled: $operationMetricsUDLFlowEnabled) {
    rows {
      orderId
      orderUuid
      workflowUuid
      orderStatus
      fulfillmentType
      salesTotal
      requestedAt
    }
    paginationResult { nextCursor nextTable }
    ordersCount
  }
}
"""

ORDER_DETAIL_QUERY = "fragment customizationFields on Orders_Customization {\n  name\n  uuid\n  __typename\n}\n\nfragment customizationOptionFields on Orders_Option {\n  name\n  quantity\n  price\n  uuid\n  support {\n    issueType\n    itemIssueType\n    __typename\n  }\n  supportV2 {\n    ...supportV2Field\n    __typename\n  }\n  __typename\n}\n\nfragment orderDeliveryPartnerFields on Orders_OrderDeliveryPartner {\n  id\n  name\n  pictureUrl\n  feedback {\n    rating\n    reason\n    __typename\n  }\n  deliveryPartnerBlockStatus {\n    blockStatus\n    __typename\n  }\n  stats {\n    satisfactionRating\n    numberOfOrdersDelivered\n    __typename\n  }\n  __typename\n}\n\nfragment currencyAmountField on CurrencyAmount {\n  amountE5\n  currencyCode\n  __typename\n}\n\nfragment supportV2Field on Orders_SupportV2 {\n  issueType\n  itemIssueType\n  subIssueType\n  quantity\n  isChargeback\n  isPotentialChargeback\n  refundValue {\n    baseAmount {\n      ...currencyAmountField\n      __typename\n    }\n    taxAmount {\n      ...currencyAmountField\n      __typename\n    }\n    feeAmount {\n      ...currencyAmountField\n      __typename\n    }\n    totalAmount {\n      ...currencyAmountField\n      __typename\n    }\n    __typename\n  }\n  chargebackValue {\n    baseAmount {\n      ...currencyAmountField\n      __typename\n    }\n    taxAmount {\n      ...currencyAmountField\n      __typename\n    }\n    feeAmount {\n      ...currencyAmountField\n      __typename\n    }\n    totalAmount {\n      ...currencyAmountField\n      __typename\n    }\n    __typename\n  }\n  imageFeedbacks {\n    url\n    processedUrl\n    accepted\n    source\n    __typename\n  }\n  resolutionFeedback {\n    text\n    __typename\n  }\n  isMerchantAtFault\n  aiExplanation\n  commentFeedbacks {\n    text\n    source\n    __typename\n  }\n  __typename\n}\n\nquery OrderDetails($workflowUUID: ID!, $metadata: Orders_OrderDetailsMetadataInput, $shouldEnableChargebackComms: Boolean, $operationMetricsUDLFlowEnabled: Boolean, $detailsRequestedByRestaurantUUID: ID) {\n  orderDetails(\n    workflowUUID: $workflowUUID\n    metadata: $metadata\n    shouldEnableChargebackComms: $shouldEnableChargebackComms\n    operationMetricsUDLFlowEnabled: $operationMetricsUDLFlowEnabled\n    detailsRequestedByRestaurantUUID: $detailsRequestedByRestaurantUUID\n  ) {\n    requestedAt\n    orderId\n    orderStateChanges {\n      changedAt\n      orderState\n      __typename\n    }\n    orderUUID\n    eater {\n      isEatsPassSubscriber\n      name\n      numOrders\n      profileURL\n      uuid\n      phone\n      phonePinCode\n      deliveryAddress\n      __typename\n    }\n    restaurant {\n      name\n      address\n      currencyCode\n      uuid\n      timezone\n      __typename\n    }\n    courier {\n      name\n      uuid\n      phone\n      __typename\n    }\n    checkoutInfo {\n      key\n      amount\n      label\n      descriptionKey\n      __typename\n    }\n    marketplaceFeeRate\n    netPayout\n    storeInstructions\n    issueSummary {\n      adjustmentAmount\n      customerRefund\n      failureReason\n      rushJobFailureReason\n      fees\n      issueType\n      numMissingItems\n      orderJobState\n      payout\n      refundNotChargedToMerchant\n      isMerchantNotYetChargedback\n      possibleChargebackAmount\n      possibleChargebackProcessingTime\n      preChargebackDisputeAction\n      willMerchantBePaid\n      statusDescription\n      orderManagementFailureDescription\n      rpgFailureTitle\n      rpgFailureDescription\n      rpgPaymentOutcomeDescription\n      __typename\n    }\n    issueSummaryV2 {\n      adjustmentAmount\n      customerRefund\n      failureReason\n      rushJobFailureReason\n      fees\n      issueType\n      numMissingItems\n      orderJobState\n      payout\n      refundNotChargedToMerchant\n      orderManagementFailureDescription\n      rpgFailureTitle\n      rpgFailureDescription\n      rpgPaymentOutcomeDescription\n      isMerchantNotYetChargedback\n      possibleChargebackAmount\n      possibleChargebackProcessingTime\n      preChargebackDisputeAction\n      willMerchantBePaid\n      statusDescription\n      itemIssueType\n      subItemIssueType\n      postDeliveryState\n      itemCustomizationIssueType\n      subItemCustomizationIssueType\n      orderDetailsChargebackCommsEnabled\n      isMerchantAtFault\n      aiExplanation\n      imageFeedbacks\n      resolutionFeedback\n      refundIssuedAt\n      chargebackIssuedAt\n      __typename\n    }\n    items {\n      customizations {\n        ...customizationFields\n        options {\n          ...customizationOptionFields\n          customizations {\n            ...customizationFields\n            options {\n              ...customizationOptionFields\n              customizations {\n                ...customizationFields\n                options {\n                  ...customizationOptionFields\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      name\n      price\n      quantity\n      support {\n        issueType\n        itemIssueType\n        __typename\n      }\n      supportV2 {\n        ...supportV2Field\n        __typename\n      }\n      uuid\n      specialInstructions\n      isRestockable\n      __typename\n    }\n    fulfillmentType\n    orderDeliveries {\n      id\n      deliveries {\n        id\n        pickedUpAt\n        deliveredAt\n        deliveryPartner {\n          ...orderDeliveryPartnerFields\n          __typename\n        }\n        previouslyAssignedDeliveryPartners {\n          ...orderDeliveryPartnerFields\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    completedAtTimestamp\n    readyByTime\n    merchantReconfirmationRequestedAtLocal\n    merchantReconfirmationConfirmedAtLocal\n    itemAwareCancellationEnabled\n    __typename\n  }\n}\n"


def gql(operation, query, variables, referer=None):
    url = f"{API_URL}?op={operation}"
    ref = referer or f"https://merchants.ubereats.com/manager/orders?restaurantUUID={STORE_UUID}"
    payload = json.dumps({"operationName": operation, "query": query, "variables": variables})
    result = subprocess.run(
        ["curl", "--silent", "--url", url,
         "-H", "accept: */*",
         "-H", "content-type: application/json",
         "-H", "origin: https://merchants.ubereats.com",
         "-H", f"referer: {ref}",
         "-H", "sec-fetch-site: same-origin",
         "-H", "x-csrf-token: x",
         "-b", COOKIES,
         "--data-raw", payload],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def list_orders(date_from, date_to):
    orders = []
    cursor = None
    next_table = "historyOrders"
    page = 1
    while True:
        pagination = {"limit": 100, "nextTable": next_table}
        if cursor:
            pagination["cursor"] = cursor
        data = gql("ordersV2", LIST_ORDERS_QUERY, {
            "filters": {
                "dateRange": {"start": date_from, "end": date_to},
                "orderIssues": [], "orderIssuesV2": [], "orderStatusFilter": [],
                "search": "", "currentTab": "historyOrders", "displayCurrencyCode": "EUR",
                "locationConstraints": {"cities": [], "countries": [], "locationUUIDs": [STORE_UUID]},
            },
            "pagination": pagination,
            "shouldEnableChargebackComms": True,
            "operationMetricsUDLFlowEnabled": True,
        })
        if data is None:
            print(f"  [page {page}: null response — cookie may be expired]")
            break
        if "errors" in data:
            print(f"  [page {page}: error — {data['errors'][0].get('message','?')[:80]}]")
            break
        result = (data.get("data") or {}).get("ordersV2", {})
        rows = result.get("rows", [])
        orders.extend(rows)
        print(f"  Page {page}: {len(rows)} orders (total so far: {len(orders)} / {result.get('ordersCount')})")
        pagination_result = result.get("paginationResult") or {}
        cursor = pagination_result.get("nextCursor")
        next_table = pagination_result.get("nextTable") or next_table
        if not cursor or not rows:
            break
        page += 1
        time.sleep(random.uniform(3, 7))
    return orders


COOKIE_EXPIRED = object()  # sentinel: auth/network failure — do NOT write null row


def get_order_detail(workflow_uuid):
    while True:
        ref = f"https://merchants.ubereats.com/manager/orders/{workflow_uuid}?restaurantUUID={STORE_UUID}"
        data = gql("OrderDetails", ORDER_DETAIL_QUERY, {
            "workflowUUID": workflow_uuid,
            "detailsRequestedByRestaurantUUID": STORE_UUID,
            "metadata": {"isEatsPassSubscriber": False, "locale": "en"},
            "shouldEnableChargebackComms": True,
        }, referer=ref)
        if data is None:
            print(" [null — cookie expired?]", end="", flush=True)
            return COOKIE_EXPIRED
        if "errors" in data:
            msg = data["errors"][0].get("message", "")
            if "rate" in msg.lower():
                print(" [rate limited, waiting 60s]", end="", flush=True)
                time.sleep(60)
                continue
            print(f" [err: {msg[:60]}]", end="", flush=True)
            return None  # data error for this order — write null row and continue
        return (data.get("data") or {}).get("orderDetails")


def extract_timestamps(order_detail):
    ts = {}
    for change in (order_detail.get("orderStateChanges") or []):
        state = change.get("orderState")
        changed_at = change.get("changedAt")
        if changed_at:
            changed_at = changed_at / 1000 if changed_at > 1e10 else changed_at
            iso = datetime.fromtimestamp(changed_at, tz=timezone.utc).isoformat()
            if state == "READY":
                ts["ready_at"] = iso
            elif state == "BEGINTRIP":
                ts["picked_up_at"] = iso
            elif state == "COMPLETED":
                ts["delivered_at"] = iso
    deliveries = []
    for od in (order_detail.get("orderDeliveries") or []):
        if isinstance(od, dict):
            deliveries.extend(od.get("deliveries") or [])
    if deliveries:
        d = deliveries[0]
        ts["picked_up_at"] = ts.get("picked_up_at") or d.get("pickedUpAt")
        ts["delivered_at"] = ts.get("delivered_at") or d.get("deliveredAt")
    return ts


if __name__ == "__main__":
    ORDERS_CACHE = "ubereats_orders_list.json"
    output_file  = "ubereats_orders_with_addresses.csv"

    if os.path.exists(ORDERS_CACHE):
        with open(ORDERS_CACHE) as f:
            orders = json.load(f)
        print(f"Loaded {len(orders)} orders from cache.")
    else:
        chunks = [
            ("2025-01-01", "2025-03-31"),
            ("2025-04-01", "2025-06-30"),
            ("2025-07-01", "2025-09-30"),
            ("2025-10-01", "2025-12-31"),
            ("2026-01-01", "2026-03-31"),
            ("2026-04-01", "2026-06-30"),
            ("2026-07-01", "2026-09-30"),
            ("2026-10-01", "2026-10-27"),
        ]
        orders = []
        for date_from, date_to in chunks:
            print(f"Fetching {date_from} → {date_to}...")
            orders += list_orders(date_from, date_to)
        with open(ORDERS_CACHE, "w") as f:
            json.dump(orders, f)
        print(f"\nTotal orders: {len(orders)} — cached to {ORDERS_CACHE}")

    if not orders:
        print("No orders. Cookie may be expired — update COOKIES and retry.")
        exit()

    done_ids = set()
    fieldnames = [
        "order_id", "workflow_uuid", "placed_at", "status", "order_value", "fulfillment_type",
        "address", "ready_at", "picked_up_at", "delivered_at",
    ]
    if os.path.exists(output_file):
        with open(output_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_ids.add(row["order_id"])
        print(f"Resuming — {len(done_ids)} already done, {len(orders) - len(done_ids)} remaining.")

    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not done_ids:
            writer.writeheader()

        for i, order in enumerate(orders):
            order_id      = order.get("orderId")
            workflow_uuid = order.get("workflowUuid")
            if order_id in done_ids:
                continue
            print(f"[{i+1}/{len(orders)}] {order_id}", end=" ", flush=True)

            detail = get_order_detail(workflow_uuid)
            if detail is COOKIE_EXPIRED:
                print("\n[STOPPED — cookie/auth failure. Update COOKIES and restart.]")
                break
            if detail is None:
                print("— no detail (genuine null)")
                writer.writerow({
                    "order_id": order_id, "workflow_uuid": workflow_uuid,
                    "placed_at": None, "status": order.get("orderStatus"),
                    "order_value": order.get("salesTotal"),
                    "fulfillment_type": order.get("fulfillmentType"),
                    "address": None, "ready_at": None,
                    "picked_up_at": None, "delivered_at": None,
                })
                f.flush()
                continue

            eater = detail.get("eater") or {}
            ts    = extract_timestamps(detail)
            placed_ts = detail.get("requestedAt") or order.get("requestedAt")
            if placed_ts and placed_ts > 1e10:
                placed_ts /= 1000
            placed_iso = datetime.fromtimestamp(placed_ts, tz=timezone.utc).isoformat() if placed_ts else None

            writer.writerow({
                "order_id":        order_id,
                "workflow_uuid":   workflow_uuid,
                "placed_at":       placed_iso,
                "status":          order.get("orderStatus"),
                "order_value":     order.get("salesTotal"),
                "fulfillment_type": order.get("fulfillmentType"),
                "address":         eater.get("deliveryAddress"),
                **ts,
            })
            f.flush()
            print(f"— {eater.get('deliveryAddress', 'no address')}")

            # every ~20 orders take a longer break, otherwise random 5-12s
            if (i + 1) % 20 == 0:
                pause = random.uniform(45, 90)
                print(f"  [pause {pause:.0f}s]")
                time.sleep(pause)
            else:
                time.sleep(random.uniform(5, 12))

    print(f"\nDone. Saved to {output_file}")
