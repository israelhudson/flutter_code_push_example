# [002] — Transcrição bruta

Transcrição **automática (ASR)** de [Firebase Remote Config (Package of the Week)](https://youtu.be/34ExOdNEMXI),
faixa `en-orig`. Extraída com `yt-dlp` em 2026-08-18.
Referência principal: [002-remote-config-package-of-the-week.md](002-remote-config-package-of-the-week.md).

> ⚠️ ASR de inglês sobre fala em inglês — bem mais confiável que a tradução automática,
> mas ainda sem pontuação e com capitalização errada (`Flags`, `B test`, `Json`, `sports` = *supports*).
> Não citar literalmente sem revisar.

---

**[00:01]** foreign can be risky even after testing the feature how can you be sure that it works before getting it into users hands and how can you be sure that users will like the new feature what you need is a way to enable a feature for a small segment of your users in the Firebase remote config package is here to help

**[00:25]** remote config is a key value store that lives in the cloud and because it lives in the cloud it allows you to change and customize your app without making users download an update when you're launching that new feature use remote config to set feature Flags you can start by launching it to a small number of your most loyal users and then slowly roll it out to the rest of your users later or maybe you want to find out if making

**[00:47]** a button red will drive more users to take the action you can use remote config to a B test that you can set up a Boolean key value pair and remote config and set the value to be true for a certain percentage of your users then when the user's device fetches the new value you can show the correct button for that segment of the audience to segment your users remote config has

**[01:09]** many built-in conditions you can work with you can make an audience segment that represents just users who use English on their device or you can make an audience segment that targets only iOS users only folks using the most recent version of your application the date time that a request is made and more you can even choose a random percentage of users that will be in an audience segment if you

**[01:31]** want to have a variety of types of users to test a new feature if you use Google analytics already you can use your analytics data to segment your Audience by any traits you're interested in like users who have made purchases in the past when setting values in the remote config console you can use strings booleans numbers or even Json blobs when you change the values in the cloud

**[01:53]** your users will see the new value the next time your app fetches from a remote config and you can fetch as often or as little as you'd like remote config caches the most recent values and sports default values and it's important to provide a default value so your app still works offline for more information on the remote config package and all flutter packages head to pub.dev
