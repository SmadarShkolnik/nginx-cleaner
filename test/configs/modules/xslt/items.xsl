<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html"/>
  <xsl:template match="/items">
    <ul><xsl:for-each select="item"><li><xsl:value-of select="."/></li></xsl:for-each></ul>
  </xsl:template>
</xsl:stylesheet>
