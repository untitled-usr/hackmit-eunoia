// load the global Cypress types
/// <reference types="cypress" />

declare namespace Cypress {
	interface Chainable {
		loginAdmin(): Chainable<Element>;
		uploadTestDocument(suffix: any): Chainable<Element>;
		deleteTestDocument(suffix: any): Chainable<Element>;
	}
}
