# Setting up the official WhatsApp Business API

You only need this if you want the app to send all approved messages in one go,
instead of you pressing Send on your phone for each parent. Until this is done,
keep using **From my phone** on the Send page. It works with no setup at all.

**Expect this to take a few days to a few weeks**, mostly waiting for Meta to
verify your business.

## 1. Create a Meta Business account and verify your business

1. Go to <https://business.facebook.com> and create a business account for
   your institute.
2. In **Business settings → Security Centre**, start **business
   verification**. Meta asks for documents showing the business exists
   (registration certificate, utility bill and so on).

## 2. Set up WhatsApp for the business

1. Go to <https://developers.facebook.com>, create an app of type
   **Business**, and add the **WhatsApp** product.
2. Add a **phone number** for sending.
   - It can't stay active in the normal WhatsApp app at the same time, unless
     you use Meta's coexistence option for the WhatsApp Business app.
   - A new SIM just for this is simplest.
3. Set the **display name** parents will see (for example your institute's
   name). Meta reviews it.
4. Add a **payment method** in WhatsApp Manager. Meta charges a small fee per
   message; see Meta's WhatsApp pricing page for the current rate for India
   ("Utility" messages).

## 3. Submit the message templates

In **WhatsApp Manager → Message templates**, create these with category
**Utility** and language **English**.

The numbers in `{{ }}` are filled in by the app. Meta does not accept a
template that starts or ends with one of them, so each template ends with a
sign-off line. Replace `<your name / institute>` with your own.

**`marks_adv_mains`**, for rounds with an Advance and a Mains exam:

```
*Advance Exam - {{1}} Marks*

Maths - {{2}}
Physics - {{3}}
Chemistry - {{4}}

*Total Marks - {{5}}*

*Mains Exam - {{6}} Marks*

Maths - {{7}}
Physics - {{8}}
Chemistry - {{9}}

*Total Marks - {{10}}*

— <your name / institute>
```

**`marks_adv`**, for rounds with only an Advance exam:

```
*Advance Exam - {{1}} Marks*

Maths - {{2}}
Physics - {{3}}
Chemistry - {{4}}

*Total Marks - {{5}}*

— <your name / institute>
```

**`marks_mains`**: the same as `marks_adv`, with "Mains Exam" instead of
"Advance Exam".

### If "Start each message with the student's name" is on

Make versions with a first line before everything else, and shift the other
numbers up by one. For example, `marks_adv_mains_named`:

```
Student: *{{1}}*

*Advance Exam - {{2}} Marks*

Maths - {{3}}
Physics - {{4}}
Chemistry - {{5}}

*Total Marks - {{6}}*

*Mains Exam - {{7}} Marks*

Maths - {{8}}
Physics - {{9}}
Chemistry - {{10}}

*Total Marks - {{11}}*

— <your name / institute>
```

**What the app sends, in order:**
- the student's name (only if the name line is on)
- then, for each exam: exam number, Maths, Physics, Chemistry, Total

## 4. Get the access details

1. In **Business settings → Users → System users**, create a system user and
   give it the WhatsApp account.
2. Generate a **permanent token** with the `whatsapp_business_messaging`
   permission. Copy it. You'll paste it into the app once, and it is never
   shown again.
3. In the developer app, under **WhatsApp → API Setup**, copy the **Phone
   number ID**.

## 5. Parents' consent

Meta requires that parents agreed to receive WhatsApp messages from you, for
example:
- a line on the admission form, or
- a parent replying "YES" to a message from you.

Keep a record of it.

## 6. Test first

The developer app comes with a free **test number** that can message up to 5
numbers you verify (for example your own). Put the test number's Phone number
ID and a token into the app, approve one message for your own number, and send
it through the API.

## 7. Fill in the app's Settings

Go to **Settings → WhatsApp Business API** and fill in:
- Phone Number ID and access token
- **API version**: check the current Graph API version in Meta's developer
  docs. The app starts with `v24.0`.
- **Template language code**: `en`
- the **template name for each kind of round**, e.g. "Advance Exam + Mains
  Exam" → `marks_adv_mains`

Then press **Save API settings**. From then on the app sends through the API automatically. To go back to sending from your own WhatsApp, press **Remove API key**.

## How sending works then

On the **Send** page press **Send all approved**. (If you ever need to, switch on **Send from my own
WhatsApp instead**.)

- The app sends one message at a time, with a short pause between them.
- It stops at once if the token is wrong or Meta says you're sending too fast.
- **Failed** messages (for example a number not on WhatsApp) can be retried.
- **Unknown — check** means WhatsApp didn't answer in time, so the message may
  or may not have arrived. The app never resends these by itself. Check the
  chat, then press **It arrived** or **Send again**.
- The app records "Accepted by WhatsApp". Blue ticks (delivered/read) would
  need the app to run on an internet server, which this version doesn't do.
