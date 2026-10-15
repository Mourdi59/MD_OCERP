# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""German wording of the commissioning demo register.

The seeder writes its checks, deficiencies and notes in English. A demo project whose locale is German
takes the same register in this wording instead, so a German walk-through does not meet English rows.
Everything here is generic wording per system type, never specific to one building.
"""

from __future__ import annotations

#: Per system type: (prefunctional checks, functional checks), in the order of the English catalogue.
CHECKS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "hvac": (
        (
            "Gerät nach den freigegebenen Werkstattzeichnungen eingebaut, die geforderten Wartungsabstände sind frei.",
            "Luftkanäle gereinigt, druckgeprüft, Leckage innerhalb der geforderten Dichtheitsklasse.",
            "Filter in der geforderten Klasse eingebaut, Differenzdruckwächter eingestellt.",
            "Schwingungsdämpfer richtig belastet, Transportsicherungen entfernt.",
            "Drehrichtung, Stromaufnahme und Überlastschutz des Motors mit dem Typenschild verglichen.",
            "Kondensatwanne mit Gefälle zum Ablauf, Siphon gefüllt.",
        ),
        (
            "Zulufttemperatur hält den Sollwert über einen Lauf von dreißig Minuten auf 1 K genau.",
            "Die Wärmerückgewinnung schaltet bei der vorgesehenen Außentemperatur um und schaltet sauber zurück.",
            "Der Ventilator fährt den gesamten Drehzahlbereich ohne Pendeln oder Störmeldung.",
            "Rauchmelder schalten das Gerät ab, die Klappe fährt in ihre Sicherheitsstellung.",
            "Luftmengen auf die Planwerte einreguliert, innerhalb der zulässigen Toleranz.",
            "Sollwertverschiebung und Nachtabsenkung folgen der schriftlichen Regelungsbeschreibung.",
        ),
    ),
    "electrical": (
        (
            "Stromkreise bezeichnet, beschriftet und mit dem Bestandsschema abgeglichen.",
            "Anzugsmomente an Sammelschienen und Kabelanschlüssen geprüft und markiert.",
            "Isolationswiderstand und Schutzleiterdurchgang an jedem Endstromkreis gemessen.",
            "Einstellungen der Schutzorgane entsprechen der Selektivitätsstudie.",
            "Schutzart des Gehäuses unverletzt, nicht benutzte Einführungsplatten verschlossen.",
        ),
        (
            "Drehfeld und Phasensymmetrie unter Last nachgewiesen.",
            "Schutzorgane lösen innerhalb der Zeiten der Selektivitätsstudie aus.",
            "Umschaltung auf die Ersatzversorgung erfolgt innerhalb der vertraglichen Unterbrechungszeit.",
            "Lastprobe mit Nennlast über die vorgegebene Dauer gehalten.",
            "Die Messung meldet die gemessene Last innerhalb der Toleranz an die Überwachung.",
        ),
    ),
    "fire": (
        (
            "Adressen von Meldern und Handfeuermeldern stimmen mit dem Bestandsplan der Meldergruppen überein.",
            "Kabeltyp, Trennung und Feuerwiderstand gegen die Leistungsbeschreibung geprüft.",
            "Leitungen gespült, druckgeprüft und hydraulisch abgenommen.",
            "Batterien bemessen, eingebaut und die Überbrückungsdauer berechnet.",
            "Schnittstellen zu Aufzügen, Klappen und Türfeststellanlagen verdrahtet und aufgelegt.",
        ),
        (
            "Jeder Melder und Handfeuermelder löst die richtige Meldergruppe an der Zentrale aus.",
            "Signalgeber erreichen in allen genutzten Bereichen den geforderten Schalldruckpegel.",
            "Die Brandfallsteuermatrix wurde vollständig durchgespielt, einschließlich Aufzugsrückruf.",
            "Entrauchungsventilatoren erreichen den Auslegungsvolumenstrom, der Treppenhausdruck bleibt im Band.",
            "Die Zentrale läuft die volle Überbrückungsdauer auf Batterie und lädt innerhalb der Vorgabe nach.",
        ),
    ),
    "plumbing": (
        (
            "Rohrleitungen druckgeprüft, der Druck wurde über die vorgegebene Zeit ohne Verlust gehalten.",
            "Anlage gespült und desinfiziert, die Wasserproben liegen vor.",
            "Dämmung und Dampfsperre durchgehend, Armaturen und Flansche gedämmt.",
            "Armaturenliste stimmt mit dem Bestand überein, jede Armatur ist beschriftet.",
            "Ausdehnungsgefäße auf den berechneten Vordruck eingestellt.",
        ),
        (
            "Warmwasser erreicht an der entferntesten Zapfstelle innerhalb einer Minute die geforderte Temperatur.",
            "Thermostatische Mischer liefern innerhalb des sicheren Temperaturbereichs.",
            "Die Druckerhöhung hält den Druck über den gesamten Auslegungsvolumenstrom.",
            "Entwässerungsstrang besteht die Luftdruckprobe, kein Verlust der Geruchsverschlüsse.",
            "Das Legionellenschutzkonzept wurde über einen vollständigen Zyklus nachgewiesen.",
        ),
    ),
    "mechanical": (
        (
            "Anlage nach Konstruktionsplan aufgestellt, ausgerichtet und verankert.",
            "Abgas- und Verbrennungsluftwege vollständig und frei.",
            "Wasseraufbereitung dosiert, die Probe des Anlagenwassers liegt innerhalb der Vorgabe.",
            "Schmutzfänger nach dem Spülen gereinigt, Differenzdrücke protokolliert.",
            "Sicherheitsventile auf die berechneten Drücke eingestellt.",
        ),
        (
            "Die Anlage moduliert über den gesamten Leistungsbereich und hält die Vorlauftemperatur.",
            "Pumpen erreichen den Auslegungspunkt, die Reservepumpe übernimmt bei Ausfall.",
            "Der Wärmeübertrager erreicht seine Auslegungsleistung bei der geplanten Grädigkeit.",
            "Verriegelungen schalten bei Durchflussausfall und Übertemperatur sicher ab.",
            "Die jahreszeitliche Regelstrategie wurde gegen die schriftliche Beschreibung nachgewiesen.",
        ),
    ),
    "controls": (
        (
            "Jeder Punkt der Datenpunktliste installiert, adressiert und mit Messwert.",
            "Feldgeräte gegen ein Referenzgerät kalibriert, Abweichungen protokolliert.",
            "Netzsegmente abgeschlossen, die Topologie entspricht dem Bestandsplan.",
            "Visualisierung entspricht der ausgeführten Anlage, keine verwaisten oder doppelten Punkte.",
            "Alarmgrenzen aus der freigegebenen Alarmliste geladen.",
        ),
        (
            "Jeder Regelkreis ist stabil und pendelt über zwei Stunden Beobachtung nicht.",
            "Zeitprogramme und Absenkbetrieb laufen genau wie in der Beschreibung.",
            "Alarme werden an der Zentrale und im Leitsystem richtig ausgelöst, gehalten und quittiert.",
            "Die Trendaufzeichnung erfasst jeden Punkt der Liste im geforderten Intervall.",
            "Das Leitsystem stellt nach kontrolliertem Spannungsausfall die gesamte Punktliste wieder her.",
        ),
    ),
    "elevator": (
        (
            "Führungsschienen innerhalb der Herstellertoleranz ausgerichtet.",
            "Schacht frei von Bauschutt, Beleuchtung und Schachtlüftung vollständig.",
            "Umgebung des Maschinenraums innerhalb des vom Antrieb geforderten Temperaturbereichs.",
            "Schachttüren eingestellt, Führungen im Eingriff, Spaltmaß an jeder Haltestelle gemessen.",
            "Fangvorrichtung und Geschwindigkeitsbegrenzer geprüft und bescheinigt.",
        ),
        (
            "Haltegenauigkeit an jeder Haltestelle innerhalb der Toleranz, beladen und leer.",
            "Volllast- und Überlastprobe durchgeführt und gegengezeichnet.",
            "Brandfall- und Evakuierungsfahrt verhalten sich wie in der Steuermatrix gefordert.",
            "Der Notruf erreicht die Überwachungsstelle und identifiziert die Kabine.",
            "Fahrkomfort gemessen, Schwingungen und Geräusche innerhalb der Vertragswerte.",
        ),
    ),
    "security": (
        (
            "Türbeschläge, Leser und Schlösser eingebaut und mit der Türliste abgeglichen.",
            "Kamerapositionen und Sichtfelder gegen den Abdeckungsplan abgestimmt.",
            "Verkabelung geprüft, beschriftet und von der Starkstromtrasse getrennt.",
            "Server der Zentrale aufgebaut, angebunden und vor der Übergabe gesichert.",
            "Zutrittsstufen und Kartengruppen aus der freigegebenen Matrix geladen.",
        ),
        (
            "Jede gesicherte Tür gewährt, verweigert und protokolliert gemäß Zutrittsmatrix.",
            "Die Brandmeldeanlage gibt die gesicherten Türen auf den Fluchtwegen frei.",
            "Aufzeichnungen erfüllen die Aufbewahrungsdauer und die geforderte Erkennungsqualität.",
            "Einbruchbereiche werden scharf und unscharf geschaltet und melden an die Leitstelle.",
            "Das System stellt nach kontrolliertem Neustart die gesamte Konfiguration wieder her.",
        ),
    ),
    "other": (
        (
            "Anlage nach dem freigegebenen Layout errichtet und mechanisch befestigt.",
            "Freischaltung, Beschriftung und Beschilderung für eine sichere Erstinbetriebnahme vollständig.",
            "Zähler eingebaut und mit dem Monitoring verbunden.",
            "Inbetriebnahmeprotokolle des Herstellers liegen vor und sind in der Dokumentation abgelegt.",
            "Schutzeinstellungen mit dem Netzbetreiber abgestimmt, wo gefordert.",
        ),
        (
            "Ertrag gegen die Auslegung unter den beobachteten Bedingungen gemessen.",
            "Bezugs- und Einspeisegrenzen verhalten sich wie im Netzanschlussvertrag gefordert.",
            "Die Anlage schaltet bei Ausfall und Wiederkehr der Versorgung sicher ab und wieder an.",
            "Das Monitoring meldet Momentanleistung und Summen an die Zentrale.",
            "Der volle Betriebszyklus wurde über einen ununterbrochenen Zeitraum nachgewiesen.",
        ),
    ),
}

#: Deficiency text per severity.
ISSUES: dict[str, tuple[str, ...]] = {
    "critical": (
        "Sicherheitsverriegelung schaltet die Anlage bei der simulierten Störung nicht ab, nach der Nacharbeit ist neu zu prüfen.",
        "Schritt der Wirkprinzip-Prüfung schlägt fehl: Die Schnittstelle fährt die angeschlossene Anlage nicht in ihre sichere Stellung.",
        "Die gemessene Leistung liegt außerhalb der vertraglichen Grenze, die Anlage kann so nicht abgenommen werden.",
    ),
    "high": (
        "Der Regelkreis pendelt um den Sollwert und ist im Beobachtungszeitraum nicht stabil geworden.",
        "Die Reserveeinheit übernimmt bei Ausfall der Betriebseinheit nicht selbsttätig.",
        "Die Störmeldung erreicht die Zentrale, wird aber im Leitsystem nicht angezeigt.",
    ),
    "medium": (
        "Zwei Feldgeräte messen außerhalb der Kalibriertoleranz und müssen neu kalibriert werden.",
        "Der Zugang zur Wartung ist durch nachfolgende Gewerke verstellt und muss freigemacht werden.",
        "Die Beschriftung stimmt in einem Abschnitt nicht mit dem Bestandsverzeichnis überein.",
    ),
    "low": (
        "Eine Visualisierungsseite zeigt noch die überholte Anlagenanordnung und ist zu aktualisieren.",
        "Eine Trendaufzeichnung läuft im falschen Intervall.",
        "In der Bestandszeichnung sind die endgültigen Armaturenstellungen noch nicht eingetragen.",
    ),
}

RESOLUTIONS: tuple[str, ...] = (
    "Vom ausführenden Unternehmen nachgearbeitet und im Beisein der Inbetriebnahmeleitung erneut geprüft.",
    "Vor Ort behoben und gegen das ursprüngliche Prüfblatt nachgewiesen.",
    "Einstellungen geändert, die betroffene Prüfung vollständig wiederholt und das Ergebnis protokolliert.",
)

#: Note beside a result that is not a plain pass, keyed by the result status.
ITEM_NOTES: dict[str, str] = {
    "na": "Für diese Ausführung nicht zutreffend.",
    "fail": "Gemessene Leistung außerhalb des zulässigen Bereichs. Nach Behebung der Mängel erneut prüfen.",
}

PREFUNCTIONAL_TITLE = "Vorprüfliste"
FUNCTIONAL_TITLE = "Funktionsprüfung"
PREFUNCTIONAL_DESCRIPTION = "Statische Prüfungen der Installation, bevor die Anlage unter Spannung gesetzt wird."
FUNCTIONAL_DESCRIPTION = "Dynamische Leistungsprüfungen im Beisein der Inbetriebnahmeleitung."
SYSTEM_DESCRIPTION = "Inbetriebnahmepflichtige Anlage, im Rahmen der Abnahme der Gebäudetechnik zu übergeben."
