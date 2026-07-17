declare module 'pdfmake/src/printer' {
  class PdfPrinter {
    constructor(fonts: Record<string, Record<string, string>>);
    createPdfKitDocument(docDefinition: any, options?: any): any;
  }
  export = PdfPrinter;
}
