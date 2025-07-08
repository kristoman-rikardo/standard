**StandardGPT**

**Om prosjektet**
Dette er et oppdrag utført av Dalai til Standard Norge/Standard Digital, som en chat med alle Standardene de forvalter. DEt er over 30 000 stk. i en Elasticsearch-database. 

**Teknologi**
Vi bruker Langchain for å ha et rammeerk for LLMene. Vi bruker stort sett GPT 4o. Vi har en egen embeddings-API på render. Vi querier Elasticsearch gjennom deres APIer, både et tekstuelt og et semantisk søk som er outputtet fra de respektive rewrite... promptene. Backenden er Python. Vi skal etterhvert bygge en frontend også, men i første omgang runner alt i CLI. 

**Flyt**
Brukeren stiller spørsmål -> Spørsmålet analyseres. Fordeles til enten rewriteWithNumb eller rewriteWithOut. Spørsmålet embeddes så, og queries mot elastic. De returnerte resultatene sendes videre til answer -> videre til validate. Hvis true printes svaret, dersom false går det tilbake til rewrite, med kommentaren som står bak i returen fra validate(eks. false // kommentar), blir med i dette promptet. Deretter må den gjennom flyten en gang til før det printes. 

**Viktige ting**
Kvalitet er mye viktigere enn hastighet. Det viktigste er å svare presist og korrekt på alle typer spørsmål.
